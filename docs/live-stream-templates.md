# Live Stream Template Customization

This feature allows customization of YouTube live stream titles and descriptions through Django templates rather than hardcoded Python strings.

## Template Location

Templates are located at:
- `tournamentcontrol/competition/match/live_stream/title.txt`
- `tournamentcontrol/competition/match/live_stream/description.txt`

## Hierarchical Override

Templates can be overridden at different levels of specificity:

1. **Global**: `match/live_stream/title.txt`
2. **Competition**: `{competition_slug}/match/live_stream/title.txt`  
3. **Season**: `{competition_slug}/{season_slug}/match/live_stream/title.txt`
4. **Division**: `{competition_slug}/{season_slug}/{division_slug}/match/live_stream/title.txt`
5. **Stage**: `{competition_slug}/{season_slug}/{division_slug}/{stage_slug}/match/live_stream/title.txt`

## Available Context Variables

- `match`: The Match object being streamed
- `competition`: Competition object
- `season`: Season object  
- `division`: Division object
- `stage`: Stage object
- `match_url`: Full URL to the match details page
- `label_only`: True when the title should leave the teams out (see
  [Titles YouTube Rejects](#titles-youtube-rejects))

## Titles YouTube Rejects

YouTube allows a broadcast title 100 characters and rejects a longer one as
`invalidTitle` ("Title is invalid"). A final between two teams still to be
decided reaches that quickly:

```
Men's 50 | Gold Medal: Winner Semi Final 1 vs Winner Semi Final 2 | Asia Pacific Seniors Touch Cup 2026
```

When a title is rejected the synchronisation renders it again in the next
shorter form and retries, in this order:

1. **Full**: the titles as they are.
2. **Short titles**: `competition`, `season`, `division` and `stage` render
   their `short_title` where one is set.
   `M50 | Gold Medal: Winner Semi Final 1 vs Winner Semi Final 2 | Asia Pacific Seniors 2026`
3. **Label only**: `label_only` is true, and the default template leaves the
   teams out of the title of a match that has a label.
   `Men's 50 | Gold Medal | Asia Pacific Seniors Touch Cup 2026`
4. **Label only, short titles**: both together.
   `M50 | Gold Medal | Asia Pacific Seniors 2026`

A form that renders a title already tried is skipped, so a season without
short titles, a match without a label and a custom template that ignores
`label_only` cost no extra requests. When every form is rejected YouTube's
error is reported.

Every synchronisation starts again from the full title. Once the teams of a
final are known, [resyncing](#resyncing-an-existing-broadcast) the broadcast
gives it the fullest title that fits.

A custom title template takes part in the label only form by testing
`label_only`:

```django
{% autoescape off %}🏆 {{ division }} Championship | {% if match.label and label_only %}{{ match.label }}{% else %}{% if match.label %}{{ match.label }}: {% endif %}{{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }}{% endif %} | {{ competition }} {{ season }}{% endautoescape %}
```

## Plain Text Output

The rendered title and description are sent to the YouTube API as plain text, so
templates must wrap their content in `{% autoescape off %}...{% endautoescape %}`.
Without it, Django's default HTML escaping turns apostrophes into `&#x27;` and
ampersands into `&amp;` in the YouTube video metadata.

## Example Templates

### Basic Title Template
```django
{% autoescape off %}{% if match.label %}{{ division }} | {{ match.label }}{% if not label_only %}: {{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }}{% endif %} | {{ competition }} {{ season }}{% else %}{{ division }} | {{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }} | {{ competition }} {{ season }}{% endif %}{% endautoescape %}
```

### Custom Competition Title
```django
{% autoescape off %}🏆 {{ division }} Championship | {% if match.label %}{{ match.label }}: {% endif %}{{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }} | {{ competition }} {{ season }}{% endautoescape %}
```

### Description Template
```django
{% autoescape off %}Live stream of the {{ division }} division of {{ competition }} {{ season }} from {{ match.play_at.ground.venue }}.

Watch {{ match.get_home_team_plain }} take on {{ match.get_away_team_plain }} on {{ match.play_at }}.

Full match details are available at {{ match_url }}

Subscribe to receive notifications of upcoming matches.{% endautoescape %}
```

## Resyncing an Existing Broadcast

When an operator changes a match's division, teams, label, or schedule after the
YouTube broadcast has been created, the public YouTube URL stays the same but the
title/description on YouTube becomes stale. To push the current match data to an
existing broadcast without creating a new URL, visit the match's
`resync-live-stream` admin URL and confirm. The admin calls the YouTube
`liveBroadcasts.update` API with the freshly rendered title and description, and
re-binds to the ground's stream if the binding has changed.