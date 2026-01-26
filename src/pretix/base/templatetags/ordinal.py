from django import template

register = template.Library()


@register.filter
def ordinal(value):
    """
    Convert an integer to its ordinal form (1st, 2nd, 3rd, 4th, etc.)
    Handles special cases like 11th, 12th, 13th correctly.
    """
    try:
        num = int(value)
        j = num % 10
        k = num % 100
        if j == 1 and k != 11:
            return f"{num}st"
        if j == 2 and k != 12:
            return f"{num}nd"
        if j == 3 and k != 13:
            return f"{num}rd"
        return f"{num}th"
    except (ValueError, TypeError):
        return value

