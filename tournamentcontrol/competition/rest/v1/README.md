# Tournament Control Competition REST API

This module provides REST API endpoints for managing tournament competitions, including live streaming capabilities for YouTube broadcasts.

## API Endpoints

The Competition API is accessible at `/api/v1/` as part of the unified REST API structure.

### Core Competition Endpoints

#### Competitions
- `GET /api/v1/competitions/` - List all competitions
- `GET /api/v1/competitions/{slug}/` - Get competition details

#### Seasons  
- `GET /api/v1/competitions/{competition_slug}/seasons/` - List seasons for competition
- `GET /api/v1/competitions/{competition_slug}/seasons/{season_slug}/` - Get season details

#### Clubs
- `GET /api/v1/clubs/` - List all clubs
- `GET /api/v1/clubs/{slug}/` - Get club details

### Live Streaming API

#### Overview
The live streaming API provides standalone endpoints for managing YouTube live stream broadcasts for tournament matches. This API requires `change_match` permission and integrates with the Google YouTube Data API v3.

#### Authentication & Permissions
- **Authentication Required**: All endpoints require user authentication
- **Permission Required**: Live streaming endpoints require `change_match` permission (not necessarily superuser)
- **YouTube Integration**: Requires valid YouTube API credentials and live streaming setup

#### Match Listing
**Endpoint**: `GET /api/v1/livestreams/`

Lists all matches with live streaming capabilities, grouped by date.

**Parameters:**
- `date__gte` (query, optional) - Filter matches from date (YYYY-MM-DD format)
- `date__lte` (query, optional) - Filter matches to date (YYYY-MM-DD format)
- `season_id` (query, optional) - Filter by specific season ID

**Response Format:**
```json
{
  "2023-06-15": [
    {
      "id": 123,
      "uuid": "123e4567-e89b-12d3-a456-426614174000",
      "round": "Round 1",
      "date": "2023-06-15", 
      "time": "14:00:00",
      "datetime": "2023-06-15T14:00:00Z",
      "is_bye": false,
      "is_washout": false,
      "home_team": {
        "id": 1,
        "title": "Team Alpha",
        "slug": "team-alpha",
        "club": {
          "title": "Alpha Sports Club",
          "short_title": "Alpha SC",
          "slug": "alpha-sports-club",
          "abbreviation": "ASC",
          "status": "active",
          "url": "http://example.com/api/v1/clubs/alpha-sports-club/",
          "facebook": "https://facebook.com/alphasc",
          "twitter": "https://twitter.com/alphasc", 
          "youtube": "https://youtube.com/alphasc",
          "website": "https://alphasc.com"
        }
      },
      "away_team": {
        "id": 2,
        "title": "Team Beta",
        "slug": "team-beta",
        "club": {
          "title": "Beta Athletic Club",
          "short_title": "Beta AC",
          "slug": "beta-athletic-club",
          "abbreviation": "BAC",
          "status": "active",
          "url": "http://example.com/api/v1/clubs/beta-athletic-club/",
          "facebook": null,
          "twitter": null,
          "youtube": null, 
          "website": "https://betaac.com"
        }
      },
      "home_team_score": 15,
      "away_team_score": 12,
      "stage": {
        "id": 1,
        "title": "Regular Season",
        "slug": "regular-season", 
        "division": {
          "id": 1,
          "title": "Premier Division",
          "slug": "premier-division",
          "season": {
            "id": 1,
            "title": "2023 Championship Season",
            "slug": "2023",
            "competition": {
              "id": 1,
              "title": "National Touch Championship", 
              "slug": "national-championship"
            }
          }
        }
      },
      "play_at": {
        "id": 1,
        "title": "Main Field",
        "address": "123 Sports Complex Drive",
        "latitude": -33.8688,
        "longitude": 151.2093,
        "suburb": "Sydney",
        "state": "NSW",
        "postcode": "2000"
      },
      "external_identifier": "youtube_broadcast_123",
      "live_stream": true,
      "live_stream_bind": "rtmp_stream_key",
      "live_stream_thumbnail": "/media/livestream/thumbnails/match_123.jpg"
    }
  ],
  "2023-06-16": [
    {
      "id": 124,
      "uuid": "234f5678-f90c-23e4-b567-537725285111",
      // ... similar structure
    }
  ]
}
```

#### Match Detail
**Endpoint**: `GET /api/v1/livestreams/{uuid}/`

Retrieves detailed information for a specific match by UUID.

**Parameters:**
- `uuid` (path) - Match UUID

**Response**: Same format as individual match in listing endpoint.

#### Stream Status Transition
**Endpoint**: `POST /api/v1/livestreams/{uuid}/transition/`

Transitions the live stream status of a specific match broadcast on YouTube.

**Parameters:**
- `uuid` (path) - Match UUID

**Request Body:**
```json
{
  "status": "live"
}
```

**Valid Status Values:**
- `testing` - Set broadcast to testing mode (viewers can't see)
- `live` - Make broadcast live and visible to viewers
- `complete` - End the broadcast

**Success Response (200):**
```json
{
  "success": true,
  "message": "Successfully transitioned to live",
  "youtube_response": {
    "id": "youtube_broadcast_123",
    "status": {
      "lifeCycleStatus": "live"
    }
  },
  "warnings": [
    "Potentially invalid transition from testing to live"
  ]
}
```

**Error Responses:**

**400 Bad Request** - Invalid status or validation error:
```json
{
  "status": ["Select a valid choice. invalid_status is not one of the available choices."]
}
```

**400 Bad Request** - Live streaming error:
```json
{
  "success": false,
  "error": "Match does not have a live stream identifier configured"
}
```

**403 Forbidden** - Insufficient permissions:
```json
{
  "detail": "You do not have permission to access live streaming features."
}
```

**404 Not Found** - Match not found or doesn't have streaming capability:
```json
{
  "detail": "Not found."
}
```

**500 Internal Server Error** - Unexpected error:
```json
{
  "success": false,
  "error": "Unexpected error: YouTube API quota exceeded"
}
```

## Response Features

### Nested Object Details
All match responses include full nested details for related objects:
- **Stage → Division → Season → Competition** hierarchy
- **Team → Club** relationships with full club details including social media links
- **Venue (play_at)** information with geographic coordinates

### Date-Based Grouping
The listing endpoint automatically groups matches by date for easy organization and display in tournament management interfaces.

### Live Stream Integration
- **YouTube Integration**: Manages YouTube live broadcasts via Google APIs
- **Stream Keys**: Provides RTMP stream keys for broadcast software
- **Thumbnails**: Includes custom thumbnail images for broadcasts
- **Status Management**: Supports full broadcast lifecycle (testing → live → complete)

## URL Naming Patterns

All endpoints use consistent Django URL naming:

```python
from django.urls import reverse

# List matches with live streaming
reverse('v1:competition:livestream-list')

# Get specific match details  
reverse('v1:competition:livestream-detail', kwargs={
    'uuid': '123e4567-e89b-12d3-a456-426614174000'
})

# Transition stream status
reverse('v1:competition:livestream-transition', kwargs={
    'uuid': '123e4567-e89b-12d3-a456-426614174000'
})
```

## Technical Implementation

### ViewSet Architecture
- **Base Class**: `ReadOnlyModelViewSet` for list/detail operations
- **Custom Actions**: `@action` decorator for transition endpoint
- **Permissions**: Custom permission checking using `permissions_required`
- **Serialization**: Context-aware serializers for nested relationships

### Query Optimization
- **Select Related**: Optimized queries with `select_related()` for nested objects
- **Filtering**: Efficient database filtering for date ranges and seasons
- **UUID Lookup**: Fast UUID-based match identification

### Error Handling
- **Graceful Degradation**: Handles missing YouTube credentials gracefully
- **Warning System**: Captures and returns API warnings for invalid transitions
- **Exception Handling**: Comprehensive error handling with appropriate HTTP status codes

## Testing

The live streaming API includes comprehensive test coverage:

- **Authentication Testing**: Verifies superuser requirement enforcement
- **CRUD Operations**: Tests all list, detail, and transition operations
- **Error Conditions**: Tests invalid data, missing matches, and API errors
- **Response Formats**: Validates JSON response structures and nested data
- **URL Resolution**: Ensures all named URLs resolve correctly

**Run Tests:**
```bash
# Run live streaming tests specifically  
tox -e dj52-py313 -- tournamentcontrol.competition.tests.test_livestream_api
```

## Integration Requirements

### YouTube API Setup
1. **Google Cloud Project**: Create project with YouTube Data API v3 enabled
2. **OAuth 2.0 Credentials**: Configure OAuth client for server-to-server authentication  
3. **Live Streaming**: Enable live streaming capability on YouTube channel
4. **Match Configuration**: Set `external_identifier` field with YouTube broadcast ID

### Django Settings
```python
# Required for live streaming functionality
INSTALLED_APPS = [
    'tournamentcontrol.competition',
    'rest_framework',
    # ... other apps
]

# YouTube API credentials (environment variables recommended)
YOUTUBE_API_KEY = 'your_youtube_api_key'
YOUTUBE_CLIENT_ID = 'your_oauth_client_id.apps.googleusercontent.com'
YOUTUBE_CLIENT_SECRET = 'your_oauth_client_secret'
```

### Match Model Requirements
For matches to appear in live streaming endpoints:
- `external_identifier` must be set (YouTube broadcast ID)
- `external_identifier` cannot be empty or null
- Match must belong to a season with `live_stream=True`

## Security Considerations

- **Permission Required**: All live streaming operations require `change_match` permission
- **YouTube Integration**: API keys and OAuth credentials should be stored securely
- **Stream Keys**: RTMP stream keys should be treated as sensitive data
- **Rate Limiting**: Consider implementing rate limiting for YouTube API calls
- **Logging**: API operations are logged for audit purposes