from django.urls import path

from .views import ItemCreateView, ItemDeleteView, ItemListView, ItemUpdateView, item_clear

app_name = "example_app"

urlpatterns = [
    path("", ItemListView.as_view(), name="item-list"),
    path("items/new/", ItemCreateView.as_view(), name="item-create"),
    path("items/<int:pk>/edit/", ItemUpdateView.as_view(), name="item-update"),
    path("items/<int:pk>/delete/", ItemDeleteView.as_view(), name="item-delete"),
    path("items/clear/", item_clear, name="item-clear"),
]
