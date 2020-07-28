Additional database indices
===========================

If you have a large pretix database, some features such as search for orders or events might turn pretty slow.
For PostgreSQL, we have compiled a list of additional database indexes that you can add to speed things up.
Just like any index, they in turn make write operations insignificantly slower and cause the database to use
more disk space.

The indexes aren't automatically created by pretix since Django does not allow us to do so only on PostgreSQL
(and they won't work on other databases). Also, they're really not necessary if you're not having tens of
thousands of records in your database.

However, this also means they won't automatically adapt if some of the referred fields change in future updates of pretix
and you might need to re-check this page and change them manually.

Here is the currently recommended set of commands::

    CREATE EXTENSION pg_trgm;

    CREATE INDEX CONCURRENTLY pretix_addidx_event_slug
        ON pretixbase_event
        USING gin (upper("slug") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_event_name
        ON pretixbase_event
        USING gin (upper("name") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_order_code
        ON pretixbase_order
        USING gin (upper("code") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_voucher_code
        ON pretixbase_voucher
        USING gin (upper("code") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_invoice_nu1
        ON "pretixbase_invoice" (UPPER("invoice_no"));
    CREATE INDEX CONCURRENTLY pretix_addidx_invoice_nu2
        ON "pretixbase_invoice" (UPPER("full_invoice_no"));
    CREATE INDEX CONCURRENTLY pretix_addidx_organizer_name
        ON pretixbase_organizer
        USING gin (upper("name") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_organizer_slug
        ON pretixbase_organizer
        USING gin (upper("slug") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_order_email
        ON pretixbase_order
        USING gin (upper("email") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_order_comment
        ON pretixbase_order
        USING gin (upper("comment") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_orderpos_name
        ON pretixbase_orderposition
        USING gin (upper("attendee_name_cached") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_orderpos_scret
        ON pretixbase_orderposition
        USING gin (upper("secret") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_orderpos_email
        ON pretixbase_orderposition
        USING gin (upper("attendee_email") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_ia_name
        ON pretixbase_invoiceaddress
        USING gin (upper("name_cached") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_ia_company
        ON pretixbase_invoiceaddress
        USING gin (upper("company") gin_trgm_ops);


Also, if you use our ``pretix-shipping`` plugin::

    CREATE INDEX CONCURRENTLY pretix_addidx_sa_name
        ON pretix_shipping_shippingaddress
        USING gin (upper("name") gin_trgm_ops);
    CREATE INDEX CONCURRENTLY pretix_addidx_sa_company
        ON pretix_shipping_shippingaddress
        USING gin (upper("company") gin_trgm_ops);

