from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import ItemForm
from .models import Item


class ItemListView(ListView):
    model = Item
    context_object_name = "items"


class ItemCreateView(CreateView):
    form_class = ItemForm
    model = Item
    success_url = reverse_lazy("example_app:item-list")


class ItemUpdateView(UpdateView):
    form_class = ItemForm
    model = Item
    success_url = reverse_lazy("example_app:item-list")


class ItemDeleteView(DeleteView):
    model = Item
    success_url = reverse_lazy("example_app:item-list")
