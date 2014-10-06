import django.dispatch

determine_availability = django.dispatch.Signal(
    providing_args=["item", "variations", "context", "cache"]
)
