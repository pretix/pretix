"""
Test views for E2E widget testing.

These views serve HTML pages with embedded widgets for testing purposes.
"""
from django.http import HttpResponse
from django.template import Template, Context
from django.views import View


class WidgetTestPageView(View):
    """
    Serves a simple HTML page with the pretix widget embedded.

    Used for E2E testing to simulate how the widget would be embedded
    in a customer's website.
    """

    def get(self, request, organizer, event):
        """Render test page with widget embedded."""
        # Build event URL
        event_url = request.build_absolute_uri(
            f"/{organizer}/{event}/"
        )

        # Build widget script URL (old version)
        widget_script_url = request.build_absolute_uri(
            f"/widget/v2.en.js"
        )

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Widget Test Page</title>
</head>
<body>
    <h1>Pretix Widget E2E Test Page</h1>

    <!-- Pretix Widget Embed -->
    <pretix-widget event="{event_url}"></pretix-widget>

    <!-- Widget Script -->
    <script type="text/javascript" src="{widget_script_url}"></script>
</body>
</html>
"""

        return HttpResponse(html_content, content_type="text/html")
