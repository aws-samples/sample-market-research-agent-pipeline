#!/bin/bash
set -e

STACK_NAME="FrontendStack"
APP_DIR="$(cd "$(dirname "$0")/newsletter-app" && pwd)"

echo "[1/4] Building the frontend app..."
cd "$APP_DIR"
npm run build

echo "[2/4] Fetching CDK outputs from stack: $STACK_NAME..."
BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?ExportName=='MRIWebsiteBucketName'].OutputValue" \
  --output text)

DISTRIBUTION_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?ExportName=='MRICloudFrontDistributionId'].OutputValue" \
  --output text)

if [ -z "$BUCKET_NAME" ] || [ -z "$DISTRIBUTION_ID" ]; then
  echo "ERROR: Could not resolve bucket name or distribution ID from stack outputs."
  echo "  BUCKET_NAME=$BUCKET_NAME"
  echo "  DISTRIBUTION_ID=$DISTRIBUTION_ID"
  exit 1
fi

echo "  Bucket:       $BUCKET_NAME"
echo "  Distribution: $DISTRIBUTION_ID"

echo "[3/4] Syncing build output to s3://$BUCKET_NAME ..."
aws s3 sync "$APP_DIR/dist" "s3://$BUCKET_NAME" --delete

echo "[4/4] Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  --no-cli-pager

echo "Done! Site is live at:"
DOMAIN=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?ExportName=='MRIWebsiteURL'].OutputValue" \
  --output text)
echo "  $DOMAIN"
