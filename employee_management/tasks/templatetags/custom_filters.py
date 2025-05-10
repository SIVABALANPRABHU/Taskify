from django import template

register = template.Library()

@register.filter
def lookup(dictionary, key):
    if isinstance(key, str):
        return dictionary.get(key, [])
    return dictionary.get(key.strftime('%Y-%m-%d'), [])