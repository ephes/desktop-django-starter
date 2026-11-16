from django.core.paginator import Paginator
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import ItemForm
from .models import Item

PAGE_SIZE = 20


class ItemReturnNavigation:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.request.GET.get("page", "")
        context["return_page"] = page if page.isascii() and page.isdigit() else ""
        return context

    def get_success_url(self):
        page = self.request.GET.get("page")
        if page:
            page = Paginator(Item.objects.all(), PAGE_SIZE).get_page(page).number
            return f"{self.success_url}?page={page}"
        return str(self.success_url)


class ItemListView(ListView):
    model = Item
    context_object_name = "items"
    paginate_by = PAGE_SIZE
    ordering = ["-updated_at", "-created_at", "-pk"]


class ItemCreateView(ItemReturnNavigation, CreateView):
    form_class = ItemForm
    model = Item
    success_url = reverse_lazy("example_app:item-list")


class ItemUpdateView(ItemReturnNavigation, UpdateView):
    form_class = ItemForm
    model = Item
    success_url = reverse_lazy("example_app:item-list")


class ItemDeleteView(ItemReturnNavigation, DeleteView):
    model = Item
    success_url = reverse_lazy("example_app:item-list")


@require_POST
def item_clear(request):
    Item.objects.all().delete()
    return JsonResponse({"cleared": True})
