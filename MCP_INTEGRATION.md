# Django MCP Server Integration

This document describes the integration of Django MCP Server with the existing DRF API in the vitriolic project.

## Overview

The Model Context Protocol (MCP) integration allows AI agents and MCP clients to interact with the tournament control competition management system alongside the existing REST API endpoints.

## What's Integrated

### MCP Query Tools

The following models are exposed as MCP query tools:

- **ClubQueryTool**: Query and retrieve club information
- **CompetitionQueryTool**: Query competitions
- **SeasonQueryTool**: Query seasons within competitions
- **DivisionQueryTool**: Query divisions within seasons  
- **StageQueryTool**: Query stages within divisions
- **TeamQueryTool**: Query teams
- **MatchQueryTool**: Query matches
- **PersonQueryTool**: Query players/persons

### MCP Endpoint

The MCP server is available at `/mcp/mcp` endpoint when using the test configuration.

## Technical Implementation

### Dependencies Added

- `django-mcp-server>=0.5.5` added to `pyproject.toml`

### Configuration Changes

1. **INSTALLED_APPS**: Added `mcp_server` and `rest_framework` 
2. **URL Configuration**: Added MCP URLs via `path("mcp/", include("mcp_server.urls"))`
3. **MCP Tools**: Created `tournamentcontrol/competition/mcp.py` with model query tools

### Settings Configuration

```python
# Django MCP Server settings
DJANGO_MCP_GLOBAL_SERVER_CONFIG = {
    "name": "vitriolic-mcp-server",
    "instructions": "MCP Server for Tournament Control Competition Management System. Provides access to clubs, competitions, seasons, divisions, stages, teams, matches, and players data.",
}

# Optional: Configure authentication for MCP endpoints
# DJANGO_MCP_AUTHENTICATION_CLASSES = ["rest_framework.authentication.SessionAuthentication"]
```

## Usage

### For MCP Clients

MCP clients can connect to the server at the `/mcp/mcp` endpoint and use the available query tools to retrieve data from the tournament management system.

### For AI Agents

AI agents supporting MCP can interact with the tournament data through the standardized MCP protocol, allowing them to:

- Query club information
- Retrieve competition data
- Access season and division details
- Get team and player information
- Query match data

### Existing REST API Compatibility

The MCP integration is designed to work alongside the existing DRF API without any conflicts. All existing REST endpoints continue to work as before.

## Testing

The integration includes comprehensive tests:

- `test_mcp_integration.py`: Tests MCP server integration
- `test_rest_api_v1.py`: Existing REST API tests (continue to pass)

Run tests with:
```bash
uvx tox -e dj52-py312 -- tournamentcontrol.competition.tests.test_mcp_integration
uvx tox -e dj52-py312 -- tournamentcontrol.competition.tests.test_rest_api_v1
```

## Benefits

1. **Dual Protocol Support**: Both REST and MCP protocols available
2. **AI Agent Integration**: Easy integration with AI agents and MCP clients
3. **Minimal Changes**: Existing codebase remains unchanged
4. **Flexible Access**: Choose the appropriate protocol for your use case

## Future Enhancements

Potential future improvements could include:

1. **DRF Endpoint Publishing**: Convert existing DRF API endpoints to MCP tools
2. **Authentication Integration**: Add OAuth2 or token-based authentication
3. **Additional Model Tools**: Expose more models as needed
4. **Custom MCP Tools**: Create specialized tools for complex operations

## Links

- [Django MCP Server Documentation](https://github.com/omarbenhamid/django-mcp-server)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)