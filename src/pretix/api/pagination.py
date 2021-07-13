from rest_framework.pagination import PageNumberPagination


class Pagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 50
