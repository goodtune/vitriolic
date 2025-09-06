# Django REST Framework API for touchtechnology.news

This module provides a REST API for the news functionality with the following endpoints:

## API Endpoints

The API is available at `/api/v1/news/` as part of the unified REST API structure and includes:

### Categories
- `GET /api/v1/news/categories/` - List all active categories
- `GET /api/v1/news/categories/{slug}/` - Get category details by slug

### Articles  
- `GET /api/v1/news/articles/` - List all active articles
- `GET /api/v1/news/articles/{slug}/` - Get article details by slug

### Translations (nested under articles)
- `GET /api/v1/news/articles/{article_slug}/translations/` - List translations for an article
- `GET /api/v1/news/articles/{article_slug}/translations/{locale}/` - Get translation details

### API Root
- `GET /api/v1/news/` - API root view with available endpoints

## Features

- **Filtering**: Only active (is_active=True) articles and categories are returned
- **Slug-based lookups**: All detail views use slugs for SEO-friendly URLs
- **Nested translations**: Article translations are accessible as nested resources
- **Standard DRF responses**: All endpoints return standard DRF JSON responses
- **Read-only API**: Currently provides read-only access to news data

## Response Format

### Category Response
```json
{
  "title": "Technology News",
  "short_title": "Tech",
  "slug": "technology-news", 
  "is_active": true
}
```

### Article List Response
```json
[
  {
    "headline": "Django REST API Created",
    "slug": "django-rest-api-created",
    "abstract": "A new REST API has been created...",
    "published": "2023-08-29T10:00:00Z",
    "byline": "Author Name",
    "is_active": true
  }
]
```

### Article Detail Response  
```json
{
  "headline": "Django REST API Created",
  "slug": "django-rest-api-created", 
  "abstract": "A new REST API has been created...",
  "published": "2023-08-29T10:00:00Z",
  "byline": "Author Name",
  "is_active": true,
  "copy": "<p>Full article content...</p>",
  "keywords": "django, rest, api",
  "image": "/media/news/article-image.jpg"
}
```

## Architecture

The API follows Django REST Framework best practices:

- **ViewSets**: Using `SlugViewSet` base class for slug-based lookups
- **Serializers**: Separate list and detail serializers for optimized responses  
- **URL Routing**: Standard DRF router with nested routing for translations
- **Permissions**: Ready for future authentication/permission implementation

## Testing

The API includes comprehensive unit tests covering:
- Endpoint functionality
- Active/inactive filtering
- Slug-based lookups
- Response format validation

Run tests with: `tox -e dj52-py312 -- touchtechnology.news.tests.test_rest_api`