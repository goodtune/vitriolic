# Data migration to populate color fields for existing records

from django.db import migrations


def populate_division_colors(apps, schema_editor):
    """Populate division colors for existing records using order-based defaults."""
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
    
    # Update divisions that have empty color (from migration 0057)
    for division in Division.objects.filter(color=""):
        # Use order-based color if available, otherwise use gray
        division.color = default_colors.get(division.order, "#6c757d")
        division.save(update_fields=["color"])


def populate_stage_colors(apps, schema_editor):
    """Populate stage colors for existing records."""
    Stage = apps.get_model("competition", "Stage")
    
    # Update stages that have empty color (from migration 0057)
    # The db_default should handle this, but we ensure it explicitly
    for stage in Stage.objects.filter(color=""):
        stage.color = "#e8f5e8"
        stage.save(update_fields=["color"])


def reverse_population(apps, schema_editor):
    """No-op reverse - we don't want to clear colors on rollback."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0057_add_color_fields"),
    ]

    operations = [
        migrations.RunPython(populate_division_colors, reverse_population),
        migrations.RunPython(populate_stage_colors, reverse_population),
    ]
