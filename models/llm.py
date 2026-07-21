"""LLM Client — 封装 LLM 调用"""
import os
import subprocess
import tempfile
import json as jsonmod


LLM_API = "https://apihub.agnes-ai.com/v1/chat/completions"
LLM_KEY = os.environ["LLM_KEY"]  # Force env var; no default to prevent leaks
LLM_MODEL = "agnes-2.0-flash"


def call_llm(text: str, schema: str, max_tokens: int = 1500) -> dict:
    """
    调用 LLM（agnes-2.0-flash），返回 JSON dict。

    Args:
        text: 输入文本
        schema: JSON Schema 描述
        max_tokens: 最大 token 数

    Returns:
        dict: LLM 返回的 JSON
    """
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": (
                "你是一个结构化知识提取专家。严格按要求的 JSON Schema 输出，不要其他内容。"
            )},
            {"role": "user", "content": f"文本：\n{text}\n\n输出JSON（严格按Schema，不要解释）：\n{schema}"}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1
    }

    # 通过临时文件传递 body（避免命令行长度限制）
    body_file = os.path.join(tempfile.gettempdir(), 'cogn_llm_v4_body.json')
    with open(body_file, 'w', encoding='utf-8') as f:
        jsonmod.dump(payload, f, ensure_ascii=False)

    try:
        r = subprocess.run(
            ['C:/Program Files/Git/mingw64/bin/curl.EXE', '-s', '--max-time', '60',
             '-H', f'Authorization: Bearer {LLM_KEY},',
             '-H', 'Content-Type: application/json',
             '--data-binary', f'@{body_file}',
             LLM_API],
            capture_output=True,
            text=True,
            errors='replace',
        )
        if r.returncode != 0:
            return {"error": f"curl failed: {r.stderr}"}
        result = jsonmod.loads(r.stdout)

        # 解析 choices[0].message.content
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        # 尝试解析 JSON（可能带 markdown 包裹）
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return jsonmod.loads(content)

    except Exception as e:
        return {"error": str(e)}
    finally:
        if os.path.exists(body_file):
            try:
                os.unlink(body_file)
            except Exception:
                pass


def extract_evidence_schema(observation_content: str, observation_title: str = "") -> dict:
    """
    LLM Evidence 提取 Schema。

    Returns JSON：
    {
      "evidence": [
        {
          "content": "...",
          "type": "quantitative|qualitative|categorical",
          "confidence": 0.0-1.0,
          "novelty": "high|medium|low",
          "importance": 0.0-1.0,
          "horizon": "immediate|short|medium|long|structural"
        }
      ],
      "binding_type": "supports|contradicts|neutral",
      "binding_strength": 0.0-1.0,
      "error_type": "missing_signal|overconfidence|regime_mismatch|horizon_mismatch|none",
      "regime": "AI_bull|value|cyclical|bear|neutral"
    }
    """
    schema = """
{
  "evidence": [
    {
      "content": "提取的证据内容（简洁）",
      "type": "quantitative|qualitative|categorical",
      "confidence": 0.8,
      "novelty": "high|medium|low",
      "importance": 0.7,
      "horizon": "immediate|short|medium|long|structural"
    }
  ],
  "binding_type": "supports|contradicts|neutral",
  "binding_strength": 0.7,
  "error_type": "none|missing_signal|overconfidence|regime_mismatch|horizon_mismatch",
  "regime": "neutral|AI_bull|value|cyclical|bear"
}
"""
    prompt = f"标题：{observation_title}\n内容：{observation_content[:3000]}"
    return call_llm(prompt, schema)
