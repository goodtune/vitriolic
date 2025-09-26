# Unified Django REST Framework API

This module provides a unified REST API entrypoint that consolidates all application APIs under a consistent, version-first URL structure.

## API Structure

All APIs are accessible under the unified API endpoint (commonly `/api/` but project-configurable) with version-first organization:

- **Root API**: `/api/` - Discoverable API root with available versions
- **Version 1**: `/api/v1/` - All v1 APIs consolidated under this namespace
- **Authentication**: `/api/api-auth/` - Django REST Framework browsable API authentication

## Available APIs

### News API (`/api/v1/news/`)
Provides access to news articles and categories.

**Endpoints:**
- `GET /api/v1/news/categories/` - List all active categories
- `GET /api/v1/news/categories/{slug}/` - Get category details
- `GET /api/v1/news/articles/` - List all active articles  
- `GET /api/v1/news/articles/{slug}/` - Get article details
- `GET /api/v1/news/articles/{article_slug}/translations/` - List article translations
- `GET /api/v1/news/articles/{article_slug}/translations/{locale}/` - Get translation details

### Competition API (`/api/v1/`)
Provides access to competition and tournament functionality.

**Core Endpoints:**
- `GET /api/v1/competitions/` - List competitions
- `GET /api/v1/competitions/{slug}/` - Get competition details
- `GET /api/v1/competitions/{slug}/seasons/` - List seasons for competition
- `GET /api/v1/competitions/{slug}/seasons/{slug}/` - Get season details
- `GET /api/v1/clubs/` - List clubs
- `GET /api/v1/clubs/{slug}/` - Get club details

### Live Streaming API (`/api/v1/`)
Provides standalone live streaming management for matches.

**Live Streaming Endpoints:**
- `GET /api/v1/livestreams/` - List matches with live streaming capability
- `GET /api/v1/livestreams/{uuid}/` - Get specific match details
- `POST /api/v1/livestreams/{uuid}/transition/` - Transition live stream status

## Features

### Dynamic API Discovery
The unified API automatically discovers and mounts APIs based on installed Django applications:

- **News API**: Mounted when `touchtechnology.news` is installed
- **Competition API**: Mounted when `tournamentcontrol.competition` is installed
- **Graceful degradation**: Missing applications don't break the API

### Consistent URL Structure
All APIs follow a consistent, version-first pattern:
```
/api/v{version}/{module}/{resource}/
```

This provides:
- **Version-first organization**: Easy to add new API versions
- **Predictable URLs**: Consistent patterns across all modules
- **User-friendly**: Slug-based lookups for all resources
- **Namespace isolation**: Each module has its own namespace (`v1:news:`, `v1:competition:`)

### Authentication & Permissions
- **Authentication**: Uses Django REST Framework's built-in authentication
- **Permissions**: Module-specific permission classes
- **Live Streaming**: Requires `change_match` permission for stream management

## Response Format

All API endpoints return standard Django REST Framework JSON responses with consistent error handling and status codes.

### API Root Response (`/api/`)
```json
{
  "v1": "http://example.com/api/v1/"
}
```

### Version Root Response (`/api/v1/`)
```json
{
  "news": "http://example.com/api/v1/news/",
  "competitions": "http://example.com/api/v1/competitions/",
  "clubs": "http://example.com/api/v1/clubs/",
  "livestreams": "http://example.com/api/v1/livestreams/"
}
```

## Live Streaming API

### Overview
The live streaming API provides endpoints for managing YouTube live stream broadcasts for tournament matches.

### Authentication
All live streaming endpoints require authentication and `change_match` permission.

### Match Listing (`GET /livestreams/`)
Returns matches grouped by date with live streaming capabilities.

**Query Parameters:**
- `date__gte`: Filter matches from this date (YYYY-MM-DD)
- `date__lte`: Filter matches up to this date (YYYY-MM-DD)
- `season_id`: Filter by specific season ID

**Response Format:**
```json
{
  "2023-06-15": [
    {
      "id": 1,
      "uuid": "123e4567-e89b-12d3-a456-426614174000",
      "round": "Round 1",
      "date": "2023-06-15",
      "time": "14:00:00",
      "datetime": "2023-06-15T14:00:00Z",
      "home_team": {
        "id": 1,
        "title": "Team A",
        "slug": "team-a",
        "club": {
          "title": "Club Name",
          "slug": "club-name"
        }
      },
      "away_team": {
        "id": 2,
        "title": "Team B", 
        "slug": "team-b",
        "club": {
          "title": "Another Club",
          "slug": "another-club"
        }
      },
      "stage": {
        "id": 1,
        "title": "Regular Season",
        "slug": "regular-season",
        "division": {
          "id": 1,
          "title": "Division 1",
          "slug": "division-1",
          "season": {
            "id": 1,
            "title": "2023 Season",
            "slug": "2023",
            "competition": {
              "id": 1,
              "title": "Championship",
              "slug": "championship"
            }
          }
        }
      },
      "external_identifier": "youtube_broadcast_id",
      "live_stream": true,
      "live_stream_bind": "stream_key",
      "live_stream_thumbnail": "/media/thumbnails/match.jpg"
    }
  ]
}
```

### Stream Transition (`POST /livestreams/{uuid}/transition/`)
Transitions the live stream status of a specific match.

**Request Body:**
```json
{
  "status": "live"
}
```

**Valid Status Values:**
- `testing` - Set broadcast to testing mode
- `live` - Go live with broadcast
- `complete` - End the broadcast

**Error Responses:**
- `400 Bad Request`: Invalid status or validation error
- `403 Forbidden`: Insufficient permissions (`change_match` required)
- `404 Not Found`: Match not found or doesn't have streaming capability
- `500 Internal Server Error`: Unexpected error (e.g., YouTube API issues)

**Response:**
```json
{
  "success": true,
  "message": "Successfully transitioned to live",
  "youtube_response": {
    "id": "youtube_broadcast_id",
    "status": {
      "lifeCycleStatus": "live"
    }
  },
  "warnings": []
}
```

## Architecture

### Modular Design
- **Base URLs**: `touchtechnology/common/rest/urls.py` - Main entrypoint
- **Version URLs**: `touchtechnology/common/rest/v1/urls.py` - Version 1 routing
- **Module APIs**: Each module provides its own REST API namespace
- **Dynamic mounting**: APIs are conditionally included based on installed apps

### URL Naming Convention
All URLs use consistent namespacing:
```python
# News API
reverse('v1:news:category-list')      # /api/v1/news/categories/
reverse('v1:news:article-detail', kwargs={'slug': 'my-article'})

# Competition API  
reverse('v1:competition:club-list')   # /api/v1/clubs/
reverse('v1:competition:livestream-list', kwargs={
    'competition_slug': 'championship',
    'season_slug': '2023'
})  # /api/v1/competitions/championship/seasons/2023/livestreams/
```

### Testing
The unified API includes comprehensive test coverage:
- **Dynamic discovery**: Tests API mounting with different app configurations
- **URL resolution**: Validates all named URL patterns resolve correctly
- **Response formats**: Ensures consistent JSON responses across all endpoints
- **Authentication**: Tests permission enforcement for protected endpoints

Run tests with:
```bash
tox -e dj52-py313 -- touchtechnology.common.tests.test_rest_api
tox -e dj52-py313 -- tournamentcontrol.competition.tests.test_livestream_api
```

## Migration from Old APIs

### Breaking Changes
- **URL Structure**: Changed from `/api/{module}/v1/` to `/api/v1/{module}/`
- **Namespacing**: Updated from `v1:category-list` to `v1:news:category-list`

### Update Your Code
```python
# Old pattern
reverse('v1:category-list')  

# New pattern  
reverse('v1:news:category-list')
```

The unified API maintains backward compatibility for response formats while providing a more consistent and discoverable URL structure.