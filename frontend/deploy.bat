@echo off
setlocal enabledelayedexpansion

set STACK_NAME=FrontendStack
set APP_DIR=%~dp0newsletter-app

echo [1/4] Building the frontend app...
cd /d "%APP_DIR%"
call npm run build
if %ERRORLEVEL% neq 0 (
    echo ERROR: Build failed.
    exit /b 1
)

echo [2/4] Fetching CDK outputs from stack: %STACK_NAME%...

for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?ExportName=='MRIWebsiteBucketName'].OutputValue" --output text') do set BUCKET_NAME=%%i

for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?ExportName=='MRICloudFrontDistributionId'].OutputValue" --output text') do set DISTRIBUTION_ID=%%i

if "%BUCKET_NAME%"=="" (
    echo ERROR: Could not resolve bucket name from stack outputs.
    exit /b 1
)
if "%DISTRIBUTION_ID%"=="" (
    echo ERROR: Could not resolve distribution ID from stack outputs.
    exit /b 1
)

echo   Bucket:       %BUCKET_NAME%
echo   Distribution: %DISTRIBUTION_ID%

echo [3/4] Syncing build output to s3://%BUCKET_NAME% ...
aws s3 sync "%APP_DIR%\dist" "s3://%BUCKET_NAME%" --delete
if %ERRORLEVEL% neq 0 (
    echo ERROR: S3 sync failed.
    exit /b 1
)

echo [4/4] Invalidating CloudFront cache...
aws cloudfront create-invalidation --distribution-id %DISTRIBUTION_ID% --paths "/*" --no-cli-pager

echo Done! Site is live at:
for /f "tokens=*" %%i in ('aws cloudformation describe-stacks --stack-name %STACK_NAME% --query "Stacks[0].Outputs[?ExportName=='MRIWebsiteURL'].OutputValue" --output text') do echo   %%i

endlocal
