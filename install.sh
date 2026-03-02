#!/usr/bin/env bash
#
# install.sh — Install custom MDI agents into an MDI 2.3 deployment
#
# Usage:
#   cd /path/to/medical-deep-insights-release-v2.3.0
#   bash /path/to/mdi-custom-agents/install.sh
#
set -euo pipefail

# Color helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Resolve script directory (where the repo was cloned)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve MDI root — must be run from inside the MDI project
MDI_ROOT="$(pwd)"
if [[ ! -f "$MDI_ROOT/agents/agent_config/agent.yaml" ]]; then
    error "Must be run from the MDI 2.3 project root directory."
    error "Expected: /path/to/medical-deep-insights-release-v2.3.0"
    exit 1
fi

info "MDI root: $MDI_ROOT"
info "Agent package: $SCRIPT_DIR"

# ─── Step 1: Copy tool files ───────────────────────────────────────────────
info "Copying tool files..."
cp -v "$SCRIPT_DIR/agents/tools/cmdb_lookup.py"         "$MDI_ROOT/agents/tools/"
cp -v "$SCRIPT_DIR/agents/tools/generate_ticket_yaml.py" "$MDI_ROOT/agents/tools/"
cp -v "$SCRIPT_DIR/agents/tools/ge_product_catalog.py"   "$MDI_ROOT/agents/tools/"

# ─── Step 2: Copy data files ──────────────────────────────────────────────
info "Copying data files..."
mkdir -p "$MDI_ROOT/agents/data"
cp -v "$SCRIPT_DIR/agents/data/cmdb.csv"                  "$MDI_ROOT/agents/data/"
cp -v "$SCRIPT_DIR/agents/data/ge_healthcare_products.csv" "$MDI_ROOT/agents/data/"

# ─── Step 3: Patch __init__.py ─────────────────────────────────────────────
INIT_FILE="$MDI_ROOT/agents/tools/__init__.py"
info "Patching $INIT_FILE..."

for IMPORT_LINE in \
    "from agents.tools.cmdb_lookup import cmdb_lookup" \
    "from agents.tools.generate_ticket_yaml import generate_ticket_yaml" \
    "from agents.tools.ge_product_catalog import ge_product_catalog"; do
    if ! grep -qF "$IMPORT_LINE" "$INIT_FILE"; then
        echo "$IMPORT_LINE" >> "$INIT_FILE"
        info "  Added: $IMPORT_LINE"
    else
        warn "  Already present: $IMPORT_LINE"
    fi
done

# ─── Step 4: Patch tool_mapping.py ────────────────────────────────────────
MAPPING_FILE="$MDI_ROOT/agents/utils/tool_mapping.py"
info "Patching $MAPPING_FILE..."

# Add imports if missing
for TOOL_NAME in cmdb_lookup generate_ticket_yaml ge_product_catalog; do
    if ! grep -qF "    $TOOL_NAME," "$MAPPING_FILE"; then
        # Insert before the closing ')' of the import block
        sed -i "/^from agents.tools import/,/)/ { /^)/ i\\    $TOOL_NAME," "}" "$MAPPING_FILE"
        info "  Added import: $TOOL_NAME"
    else
        warn "  Import already present: $TOOL_NAME"
    fi
done

# Add TOOL_MAP entries if missing
if ! grep -q '"cmdb_lookup"' "$MAPPING_FILE"; then
    sed -i '/^}/i\
    "cmdb_lookup": {\
        "tool": cmdb_lookup,\
        "display_name": "CMDB Lookup",\
        "description": "Query CMDB for application details including support team, business unit, and criticality by application ID or name."\
    },\
    "generate_ticket_yaml": {\
        "tool": generate_ticket_yaml,\
        "display_name": "Generate Ticket YAML",\
        "description": "Generate a structured support ticket YAML file from extracted issue details, CMDB data, and severity assessment."\
    },' "$MAPPING_FILE"
    info "  Added TOOL_MAP entries: cmdb_lookup, generate_ticket_yaml"
else
    warn "  TOOL_MAP entry cmdb_lookup already present"
fi

if ! grep -q '"ge_product_catalog"' "$MAPPING_FILE"; then
    sed -i '/^}/i\
    "ge_product_catalog": {\
        "tool": ge_product_catalog,\
        "display_name": "GE Product Catalog",\
        "description": "Query GE Healthcare product catalog for imaging equipment details including MRI, CT, and ultrasound systems."\
    },' "$MAPPING_FILE"
    info "  Added TOOL_MAP entry: ge_product_catalog"
else
    warn "  TOOL_MAP entry ge_product_catalog already present"
fi

# ─── Step 5: Append agent configs to agent.yaml ──────────────────────────
AGENT_YAML="$MDI_ROOT/agents/agent_config/agent.yaml"
info "Patching $AGENT_YAML..."

for AGENT_ID in it_ticket_agent medical_device_bidding_agent; do
    if grep -q "agent_id: $AGENT_ID" "$AGENT_YAML"; then
        warn "  Agent $AGENT_ID already exists in agent.yaml — skipping"
    else
        echo "" >> "$AGENT_YAML"
        # Indent the YAML list item properly under agent_configs
        sed 's/^/  /' "$SCRIPT_DIR/agents/agent_config/${AGENT_ID}.yaml" >> "$AGENT_YAML"
        info "  Appended agent config: $AGENT_ID"
    fi
done

# ─── Step 6: Validate ────────────────────────────────────────────────────
info "Validating..."

python3 -c "
import py_compile, sys
for f in [
    'agents/tools/cmdb_lookup.py',
    'agents/tools/generate_ticket_yaml.py',
    'agents/tools/ge_product_catalog.py',
    'agents/utils/tool_mapping.py',
    'agents/tools/__init__.py',
]:
    try:
        py_compile.compile(f, doraise=True)
        print(f'  ✓ {f}')
    except py_compile.PyCompileError as e:
        print(f'  ✗ {f}: {e}', file=sys.stderr)
        sys.exit(1)
" || { error "Python syntax validation failed!"; exit 1; }

python3 -c "
import yaml
yaml.safe_load(open('$AGENT_YAML'))
print('  ✓ agent.yaml')
" || { error "YAML validation failed!"; exit 1; }

echo ""
info "Installation complete! Next steps:"
echo ""
echo "  1. Rebuild Docker image:"
echo "     export DOCKER_DEFAULT_PLATFORM=\"linux/amd64\""
echo "     docker build -f docker/service.dockerfile -t <ECR_REPO>:<TAG> ."
echo ""
echo "  2. Push and deploy to ECS:"
echo "     docker push <ECR_REPO>:<TAG>"
echo "     aws ecs update-service --cluster <CLUSTER> --service <SERVICE> --force-new-deployment"
echo ""
echo "  3. Import agent engine in the Insights Portal:"
echo "     - Go to /agent-engines → Import"
echo "     - Engine Address: http://<ALB_DNS> (no trailing space!)"
echo "     - Engine Type: MDI (Strands)"
echo ""
