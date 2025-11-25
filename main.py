import asyncio
import json
from datetime import datetime

from config import logger
from repository import SigNozRepository
from analyzer import BatchAnalyzer


async def main():
    """Main execution flow with proper resource management"""
    repo = SigNozRepository()
    analyzer = BatchAnalyzer()

    try:
        logger.info("🚀 Starting Error Analysis Pipeline...")

        # Step 1: Fetch errors
        errors = await repo.fetch_errors(limit=10, time_window_minutes=60)

        if not errors:
            logger.info("✅ No significant errors found in the last hour")
            return

        # Step 2: Analyze with AI
        logger.info(f"🤖 Analyzing {len(errors)} error groups...")
        result = await analyzer.analyze_batch(errors)

        # Step 3: Output results
        print("\n" + "="*60)
        print("🎯 ERROR ANALYSIS REPORT")
        print("="*60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("="*60 + "\n")

        # Optional: Save to file
        output_file = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(f"/home/claude/{output_file}", "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Report saved to {output_file}")

    except KeyboardInterrupt:
        logger.info("⚠️  Process interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        await repo.close()
        logger.info("👋 Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
