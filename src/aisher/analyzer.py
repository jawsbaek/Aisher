import asyncio
import json
import logging
from typing import List, Dict, Any
from datetime import datetime
from litellm import acompletion

from .config import settings, logger
from .models import ErrorLog
from .toon_formatter import ToonFormatter


class BatchAnalyzer:
    """AI-powered batch analysis with TOON format optimization"""

    async def analyze_batch(
        self,
        errors: List[ErrorLog],
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Analyze error batch using LLM with TOON format.

        Args:
            errors: List of error logs to analyze
            retry_count: Current retry attempt

        Returns:
            Analysis result as JSON dict
        """
        # Convert to TOON format
        toon_payload = ToonFormatter.format_tabular(errors, array_name="exception_logs")

        # Token estimation (rough)
        token_estimate = len(toon_payload) // 4
        logger.info(f"📋 TOON Payload: {len(toon_payload)} chars (~{token_estimate} tokens)")

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"\n{'-'*60}\n{toon_payload}\n{'-'*60}")

        system_prompt = """You are a Principal SRE analyzing production errors.

Input format: TOON (Token-Oriented Object Notation)
- Format: array_name[count]{columns}:
- Each line after header is a data row

Task:
1. Identify the PRIMARY root cause (not symptoms)
2. Assess severity and business impact
3. Provide actionable remediation steps
4. Suggest monitoring improvements

Output as JSON:
{
  "root_cause": "string",
  "severity": "critical|high|medium|low",
  "affected_services": ["service1", "service2"],
  "remediation": {
    "immediate": ["action1", "action2"],
    "long_term": ["improvement1"]
  },
  "monitoring_gaps": ["metric1", "alert2"]
}"""

        try:
            response = await asyncio.wait_for(
                acompletion(
                    model=settings.LLM_MODEL,
                    api_key=settings.OPENAI_API_KEY.get_secret_value(),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Analyze these errors:\n\n{toon_payload}"}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=2000
                ),
                timeout=settings.LLM_TIMEOUT
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            # Add metadata
            result["_meta"] = {
                "model": settings.LLM_MODEL,
                "analyzed_at": datetime.utcnow().isoformat(),
                "error_count": len(errors)
            }

            logger.info("✅ Analysis completed successfully")
            return result

        except asyncio.TimeoutError:
            logger.error(f"⏱️  LLM timeout after {settings.LLM_TIMEOUT}s")
            if retry_count < settings.MAX_RETRIES:
                logger.info(f"🔄 Retrying... ({retry_count + 1}/{settings.MAX_RETRIES})")
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                return await self.analyze_batch(errors, retry_count + 1)
            return {"error": "LLM Analysis Timed Out", "retry_exhausted": True}

        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON response: {e}")
            return {"error": "Invalid LLM response format", "details": str(e)}

        except Exception as e:
            logger.error(f"❌ LLM Error: {e}", exc_info=True)
            return {"error": f"LLM Interaction Failed: {str(e)}"}
