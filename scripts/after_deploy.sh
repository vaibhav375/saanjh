#!/bin/sh
# After `sam deploy`: publish the page, upload VIIRS ground truth, and replay seasons in the cloud.
# usage: scripts/after_deploy.sh [first_day last_day step_min]   (default: 2024-10-15 2024-11-30 10)
set -e
cd "$(dirname "$0")/.."
out() { aws cloudformation describe-stacks --stack-name saanjh --region us-east-1 \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
DATA=$(out DataBucket); SITE=$(out SiteBucket); SM=$(out ReplayStateMachine); URL=$(out SiteUrl)

# Until the first live run publishes tonight.json, show the 18 Nov 2024 replay.
aws s3 cp site/tonight.json "s3://$SITE/tonight.json" --content-type application/json
aws s3 cp data/firms/viirs_snpp_2024_punjab_both_octnov.csv "s3://$DATA/viirs/punjab_both.csv"

FIRST=${1:-2024-10-15}; LAST=${2:-2024-11-30}; STEP=${3:-10}
DAYS=$(python3 -c "
import json, sys
from datetime import date, timedelta
a, b = date.fromisoformat('$FIRST'), date.fromisoformat('$LAST')
print(json.dumps({'days': [{'day': str(a + timedelta(n)), 'step_min': $STEP} for n in range((b - a).days + 1)]}))")
aws stepfunctions start-execution --state-machine-arn "$SM" --region us-east-1 \
  --name "replay-$FIRST-$LAST-$STEP-$(date +%s)" --input "$DAYS" --query executionArn --output text
echo "Page: $URL"
