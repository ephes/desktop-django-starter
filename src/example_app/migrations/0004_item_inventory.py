from django.db import migrations, models

ITEM_EVENTS = ("INSERT", "UPDATE", "DELETE")
BUMP_GENERATION = """
    INSERT INTO example_app_iteminventory (id, generation)
    VALUES (1, lower(hex(randomblob(16))))
    ON CONFLICT(id) DO UPDATE SET generation = excluded.generation;
"""


class Migration(migrations.Migration):
    dependencies = [("example_app", "0003_alter_item_status")]

    operations = [
        migrations.CreateModel(
            name="ItemInventory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("generation", models.CharField(max_length=32)),
            ],
        ),
        migrations.RunSQL(
            sql=[
                BUMP_GENERATION,
                *[
                    f"""
                    CREATE TRIGGER example_app_inventory_after_{event.lower()}
                    AFTER {event} ON example_app_item
                    BEGIN
                        {BUMP_GENERATION}
                    END;
                    """
                    for event in ITEM_EVENTS
                ],
            ],
            reverse_sql=[
                f"DROP TRIGGER example_app_inventory_after_{event.lower()};"
                for event in ITEM_EVENTS
            ],
        ),
    ]
