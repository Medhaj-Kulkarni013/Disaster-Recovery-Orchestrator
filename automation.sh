#!/bin/bash
 
echo "🔐 Logging in to SAP BTP CLI..."
btp login --url https://cli.btp.cloud.sap

if [ $? -ne 0 ]; then
  echo "❌ Login failed."
  exit 1
fi
 
# === Generate Unique Identifiers ===
UUID_SUFFIX=$(cat /proc/sys/kernel/random/uuid | cut -d'-' -f1)
TIMESTAMP=$(date +%s)
 
SUBACCOUNT_SUBDOMAIN="subacc-${UUID_SUFFIX}-${TIMESTAMP}"
SUBACCOUNT_DISPLAY_NAME="Subaccount ${UUID_SUFFIX} ${TIMESTAMP}"
CF_ORG_NAME="org-${UUID_SUFFIX}-${TIMESTAMP}"
SPACE_NAME="dev"
CF_MEMORY=1
SELECTED_REGION="us10"
 
echo "Generated:"
echo "  - Subdomain: $SUBACCOUNT_SUBDOMAIN"
echo "  - Display Name: $SUBACCOUNT_DISPLAY_NAME"
echo "  - CF Org Name: $CF_ORG_NAME"
echo "📦 Creating subaccount in region: $SELECTED_REGION"

btp create accounts/subaccount \
  --subdomain "$SUBACCOUNT_SUBDOMAIN" \
  --display-name "$SUBACCOUNT_DISPLAY_NAME" \
  --region "$SELECTED_REGION"

echo "⏳ Waiting for subaccount provisioning..."
sleep 35
 
# === Get Subaccount ID ===
SUBACC_ID=$(btp list accounts/subaccount | grep "$SUBACCOUNT_SUBDOMAIN" | awk '{print $1}')
if [ -z "$SUBACC_ID" ]; then
  echo "❌ Failed to retrieve Subaccount ID."
  exit 1
fi

echo "✅ Subaccount ID: $SUBACC_ID"
 
# === Assign Entitlement ===
echo "📦 Assigning entitlement..."
btp assign accounts/entitlement \
  --to-subaccount "$SUBACC_ID" \
  --for-service "APPLICATION_RUNTIME" \
  --plan "MEMORY" \
  --amount "$CF_MEMORY"
 
sleep 5
 
# === Enable Cloud Foundry ===
echo "🔧 Enabling Cloud Foundry with Org: $CF_ORG_NAME..."
btp create accounts/environment-instance \
  --subaccount "$SUBACC_ID" \
  --display-name "$SUBACCOUNT_SUBDOMAIN" \
  --environment "cloudfoundry" \
  --service "cloudfoundry" \
  --plan "trial" \
  --parameters '{"instance_name": "'$CF_ORG_NAME'"}'
 
echo "⏳ Waiting for Cloud Foundry environment to be ready..."

sleep 20
 
# === Fetch CF Landscape and API ===
LANDSCAPE=$(btp list accounts/environment-instance --subaccount "$SUBACC_ID" | tail -n +3 | awk ' NR>2 {print $NF}')
if [ -z "$LANDSCAPE" ]; then
  echo "❌ Cloud Foundry landscape not found."
  exit 1
fi
 
# ✅ FIXED: convert cf-us10-001 → cf.us10-001
LANDSCAPE_MODIFIED="cf.${LANDSCAPE#cf-}"
CF_API="https://api.${LANDSCAPE_MODIFIED}.hana.ondemand.com"


echo "✅ CF API Endpoint: $CF_API"

# === Login to Cloud Foundry via SSO ===
echo "🔐 Logging into Cloud Foundry and targeting the org"
# cf login -a "$CF_API" --sso 
cf login -a "$CF_API" -u "medhkulkarni.ext@deloitte.com" -p "Deloitte@2025" -o "$CF_ORG_NAME"
if [ $? -ne 0 ]; then
  echo "❌ CF login failed."
  exit 1
fi

# === Create Space ===
echo "🏗️ Creating space: $SPACE_NAME"
cf create-space "$SPACE_NAME"
cf target -s "$SPACE_NAME"
 
if [ $? -ne 0 ]; then
  echo "❌ Failed to create space."
  exit 1
fi

echo "✅ Space '$SPACE_NAME' created successfully."
 
# === Deploy Python App ===
APP_DIR="./hello-world"
APP_NAME="hello-python"
echo "🚀 Deploying app: $APP_NAME"
cd ..
cd "$APP_DIR"
cf push "$APP_NAME"