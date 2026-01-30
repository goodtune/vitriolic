# Data migration to populate color fields for existing records

from django.db import migrations


def populate_division_colors(apps, schema_editor):
    """
    Populate division colors for existing records using order-based defaults.
    
    Note: Migration 0057 adds the color field with a callable default, but that only
    applies to NEW instances created after the migration. Existing records need to be
    updated here.
    """
    Division = apps.get_model("competition", "Division")
    
    # Default colors based on division order (matching original CSS)
    default_colors = {
        1: "#e74c3c",  # Red
        2: "#3498db",  # Blue
        3: "#2ecc71",  # Green
        4: "#f39c12",  # Orange
        5: "#9b59b6",  # Purple
        6: "#1abc9c",  # Teal
        7: "#e67e22",  # Dark Orange
        8: "#34495e",  # Dark Gray
    }
    
    # Update all divisions that don't have a color set
    # (which should be all existing ones after migration 0057)
    for division in Division.objects.all():
        if not division.color:
            # Use order-based color if available, otherwise use gray
            division.color = default_colors.get(division.order, "#6c757d")
            division.save(update_fields=["color"])


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0057_add_color_fields"),
    ]

    operations = [
        migrations.RunPython(
            populate_division_colors, 
            reverse_code=migrations.RunPython.noop
        ),
        # Note: Stage colors are handled by db_default in migration 0057,
        # so no data migration needed for stages
    ]
