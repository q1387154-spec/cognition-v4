"""Observation Engine — 信息摄取（新闻/公告/财报/研报/政策）"""
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from core import Observation, ObservationSource
from .base_engine import BaseEngine


class ObservationEngine(BaseEngine):
    """Observation Engine：外部信息 → Observation Entity。"""

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context 可包含：
          - sources: List[dict]  — 原始信息列表
          - wiki_dir: str       — Wiki raw/sources 目录

        输出 context 新增：
          - observations: List[Observation]
        """
        self.info("Observation Engine 开始运行")
        sources = context.get("sources", [])
        wiki_dir = context.get("wiki_dir")

        observations = []
        seen_fingerprints = set()

        # 如果有 wiki_dir，从 md 文件读取
        if wiki_dir:
            md_sources = self._ingest_wiki_sources(wiki_dir)
            sources = sources + md_sources

        for src in sources:
            obs = self._create_observation(src)
            if obs is None:
                continue
            fp = obs.fingerprint()
            if fp in seen_fingerprints:
                self.info(f"去重跳过: {obs.title or obs.id}")
                continue
            seen_fingerprints.add(fp)
            observations.append(obs)

        context["observations"] = observations
        self.info(f"Observation Engine 完成: {len(observations)} 条新 Observation")
        return context

    def _ingest_wiki_sources(self, wiki_dir: str) -> List[dict]:
        """从 Wiki raw/sources/*.md 摄取信息。"""
        sources = []
        wiki_path = Path(wiki_dir)
        if not wiki_path.exists():
            return sources
        for md_file in wiki_path.glob("raw/sources/*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                # 提取 frontmatter title
                title = ""
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end > 0:
                        front = content[3:end]
                        for line in front.splitlines():
                            if line.startswith("title:"):
                                title = line.split(":", 1)[1].strip().strip('"')
                sources.append({
                    "source": self._detect_source_type(md_file.name),
                    "raw_content": content,
                    "title": title or md_file.stem,
                    "url": str(md_file),
                    "timestamp": datetime.now(),
                })
            except Exception as e:
                self.warning(f"读取文件失败 {md_file}: {e}")
        return sources

    def _detect_source_type(self, filename: str) -> ObservationSource:
        name_lower = filename.lower()
        if "财报" in name_lower or "中报" in name_lower or "年报" in name_lower:
            return ObservationSource.FINANCIAL_REPORT
        if "研报" in name_lower:
            return ObservationSource.RESEARCH_REPORT
        if "公告" in name_lower or "新闻" in name_lower:
            return ObservationSource.NEWS
        if "政策" in name_lower:
            return ObservationSource.POLICY
        return ObservationSource.OTHER

    def _create_observation(self, src: dict) -> Optional[Observation]:
        """将原始字典转换为 Observation Entity。"""
        try:
            source = src.get("source")
            if isinstance(source, str):
                source = ObservationSource(source)

            content = src.get("raw_content", "")
            if not content or len(content.strip()) < 20:
                return None

            # 生成确定性 ID
            id = Observation.generate_id(
                source.value if isinstance(source, ObservationSource) else str(source),
                src.get("title", "")[:50],
                str(src.get("timestamp", "")),
            )

            return Observation(
                id=id,
                source=source,
                url=src.get("url"),
                raw_content=content[:10000],  # 截断超长内容
                title=src.get("title"),
                timestamp=src.get("timestamp", datetime.now()),
                metadata=src.get("metadata", {}),
                tags=src.get("tags", []),
            )
        except Exception as e:
            self.warning(f"创建 Observation 失败: {e}")
            return None
