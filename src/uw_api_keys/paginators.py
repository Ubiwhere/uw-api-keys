from django.core.paginator import Paginator
from django.db import connections
from django.utils.functional import cached_property


class EstimatedCountPaginator(Paginator):
    """On PostgreSQL, uses the planner's row estimate for unfiltered querysets
    instead of a full `COUNT(*)`."""

    @cached_property
    def count(self) -> int:
        queryset = self.object_list
        if hasattr(queryset, "query") and not queryset.query.where:
            connection = connections[queryset.db]
            if connection.vendor == "postgresql":
                table = connection.ops.quote_name(queryset.model._meta.db_table)
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT reltuples::bigint FROM pg_class WHERE oid = %s::regclass",
                        [table],
                    )
                    estimate = cursor.fetchone()[0]
                if estimate >= 0:
                    return estimate
        return super().count
