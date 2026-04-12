from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("example_app", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DemoContentState",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "key",
                    models.CharField(
                        choices=[("first_run_pony_seed", "First-run pony seed")],
                        max_length=64,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
