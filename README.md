# MDI 2.3 Custom Agent Extensions

Two custom agents for [Medical Deep Insights (MDI) 2.3](https://github.com/anthropics/medical-deep-insights):

| Agent | Description |
|-------|-------------|
| **IT Support Ticket Generator** | Parses IT incident emails (PDF), queries CMDB for app details, assesses severity, generates structured YAML tickets |
| **Medical Device Bidding Agent** | Searches Chinese medical device (MRI/CT/Ultrasound) bidding announcements, matches GE Healthcare products, provides competitive bidding recommendations |

## What's Included

```
mdi-custom-agents/
├── agents/
│   ├── tools/
│   │   ├── cmdb_lookup.py              # CMDB application lookup
│   │   ├── generate_ticket_yaml.py     # Ticket YAML generator
│   │   └── ge_product_catalog.py       # GE Healthcare product catalog search
│   ├── data/
│   │   ├── cmdb.csv                    # Sample CMDB (15 applications)
│   │   └── ge_healthcare_products.csv  # GE imaging products (21 products)
│   └── agent_config/
│       ├── it_ticket_agent.yaml        # IT ticket agent config snippet
│       └── medical_device_bidding_agent.yaml  # Bidding agent config snippet
├── install.sh                          # Automated installer
└── README.md
```

## Quick Install

### Prerequisites

- MDI 2.3 backend (`medical-deep-insights-release-v2.3.0`) already set up
- Python 3.11+ with `pyyaml` available
- `TAVILY_API_KEY` configured in `.env` (required for `search_google`)

### Steps

```bash
# 1. Clone this repo
git clone https://github.com/xiaobing9520-creator/mdi-custom-agents.git

# 2. cd into your MDI 2.3 backend root
cd /path/to/medical-deep-insights-release-v2.3.0

# 3. Run the installer
bash /path/to/mdi-custom-agents/install.sh

# 4. Rebuild & deploy Docker image
export DOCKER_DEFAULT_PLATFORM="linux/amd64"
docker build -f docker/service.dockerfile -t <ECR_REPO>:<TAG> .
docker push <ECR_REPO>:<TAG>

# 5. Update the DeepInsightAlb ECS service (MDI Agent Engine only)
#    Find your cluster & service names (they contain long CDK-generated suffixes):
aws ecs list-clusters | grep -i deepinsightalb
aws ecs list-services --cluster <CLUSTER_FROM_ABOVE>
#    Then update:
aws ecs update-service --cluster <CLUSTER> --service <SERVICE> --force-new-deployment
```

> **Which ECS service?** A full MDI deployment has multiple ECS clusters. Only the
> **DeepInsightAlb** cluster needs updating — it runs the MDI Agent Engine
> (FastAPI + Strands) where `agent.yaml` and tools are deployed.
>
> CDK generates long names with random suffixes, for example:
> - **Cluster**: `DeepInsightAlb-DeepInsightAlb...ClusterXXXX-xxxxxxxx`
> - **Service**: `DeepInsightAlb-DeepInsightAlb...EcsServiceXXXX-xxxxxxxx`
>
> Use `aws ecs list-clusters` and look for the one containing **`DeepInsightAlb`**.
>
> | Name prefix | Component | Update needed? |
> |-------------|-----------|----------------|
> | `DeepInsightAlb-*` | MDI Agent Engine (FastAPI + Strands agents) | **Yes** — this is where your custom agents run |
> | `MDIA-ServiceStack*` | Insights Portal BFF (NestJS) | No |
> | `MDIA-TranslationStack*` | Translation engine | No |
> | `MDIA-InkAiInternalCore*` | Core writing engine | No |

### Import in Insights Portal

1. Navigate to `/agent-engines` in the portal
2. Click **Import**
3. Fill in:
   - **Name**: Any descriptive name
   - **Engine Address**: `http://<ALB_DNS>` (no trailing space!)
   - **API Key**: Your MDI API key (from Secrets Manager)
4. Click **Import** — the portal will auto-discover both agents

## Manual Install

If you prefer to install manually instead of using the script:

### 1. Copy files

```bash
# From your MDI 2.3 root directory:
cp <repo>/agents/tools/*.py         agents/tools/
cp <repo>/agents/data/*.csv         agents/data/
```

### 2. Register tools in `agents/tools/__init__.py`

Add these lines:

```python
from agents.tools.cmdb_lookup import cmdb_lookup
from agents.tools.generate_ticket_yaml import generate_ticket_yaml
from agents.tools.ge_product_catalog import ge_product_catalog
```

### 3. Register tools in `agents/utils/tool_mapping.py`

Add to the import block:

```python
from agents.tools import (
    # ... existing imports ...
    cmdb_lookup,
    generate_ticket_yaml,
    ge_product_catalog,
)
```

Add to `TOOL_MAP`:

```python
TOOL_MAP = {
    # ... existing entries ...
    "cmdb_lookup": {
        "tool": cmdb_lookup,
        "display_name": "CMDB Lookup",
        "description": "Query CMDB for application details including support team, business unit, and criticality by application ID or name."
    },
    "generate_ticket_yaml": {
        "tool": generate_ticket_yaml,
        "display_name": "Generate Ticket YAML",
        "description": "Generate a structured support ticket YAML file from extracted issue details, CMDB data, and severity assessment."
    },
    "ge_product_catalog": {
        "tool": ge_product_catalog,
        "display_name": "GE Product Catalog",
        "description": "Query GE Healthcare product catalog for imaging equipment details including MRI, CT, and ultrasound systems."
    },
}
```

### 4. Append agent configs to `agents/agent_config/agent.yaml`

Copy the contents of `agents/agent_config/it_ticket_agent.yaml` and `agents/agent_config/medical_device_bidding_agent.yaml` into the `agent_configs:` section of your `agent.yaml`.

### 5. Rebuild and deploy

See steps 4-5 in Quick Install above.

## Agent Details

### IT Support Ticket Generator

**Tools**: `get_uploaded_file`, `cmdb_lookup`, `generate_ticket_yaml`, `current_time`, `stop`

**Workflow**:
1. User uploads a PDF incident email
2. Agent extracts reporter info, application name, issue description
3. Queries CMDB to find support team and system criticality
4. Determines severity (P1-P4) based on issue + system criticality
5. Presents analysis, pauses for user confirmation
6. Generates structured YAML ticket

**Customization**: Replace `agents/data/cmdb.csv` with your own CMDB data. Same CSV schema: `app_id,app_name,support_team,team_email,business_unit,criticality`. Or set `CMDB_FILE_PATH` env var to point to an external file.

### Medical Device Bidding Agent

**Tools**: `search_google`, `ge_product_catalog`, `current_time`, `get_uploaded_file`, `stop`, `calculator`

**Workflow**:
1. Gets current date for time-based filtering
2. Constructs Chinese search queries targeting government procurement sites (ccgp.gov.cn, ggzy.gov.cn)
3. Displays bidding results with source links, pauses for confirmation
4. Looks up matching GE Healthcare products from catalog
5. Generates competitive analysis: product recommendations, advantages, pricing strategy, competitor analysis

**Customization**: Replace `agents/data/ge_healthcare_products.csv` with your own product catalog. Or set `GE_PRODUCT_CATALOG_PATH` env var. CSV schema: `product_id,product_name,category,model_series,description,key_features,target_department,certifications,competitive_advantages`.

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `TAVILY_API_KEY` | Yes | — | Powers `search_google` in the bidding agent |
| `CMDB_FILE_PATH` | No | `agents/data/cmdb.csv` | Override CMDB data location |
| `GE_PRODUCT_CATALOG_PATH` | No | `agents/data/ge_healthcare_products.csv` | Override product catalog location |

## Compatibility

Tested with MDI 2.3.0 (`medical-deep-insights-release-v2.3.0`). Requires the Strands Agents framework with the standard tool discovery mechanism.
