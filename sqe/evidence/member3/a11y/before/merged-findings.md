# Accessibility findings (before)

59 unique element-level issues across 3 screens; 31 were found by both tools and are counted once.

## By rule

| Rule | Impact | WCAG | Issues | Found by both | Screens | Problem |
|---|---|---|---|---|---|---|
| image-alt | critical | wcag2a wcag111 | 3 | 3 | S1, S2, S3 | Images must have alternative text |
| color-contrast | serious | wcag2aa wcag143 | 6 | 6 | S1, S2, S3 | Elements must meet minimum color contrast ratio thresholds |
| html-has-lang | serious | wcag2a wcag311 | 3 | 3 | S1, S2, S3 | <html> element must have a lang attribute |
| link-in-text-block | serious | wcag2a wcag141 | 3 | 3 | S1, S2, S3 | Links must be distinguishable without relying on color |
| link-name | serious | wcag2a wcag244 wcag412 | 12 | 12 | S1, S2, S3 | Links must have discernible text |
| heading-order | moderate | - | 1 | 1 | S1 | Heading levels should only increase by one |
| landmark-one-main | moderate | - | 3 | 3 | S1, S2, S3 | Document should have one main landmark |
| landmark-unique | moderate | - | 3 | 0 | S1, S2, S3 | Landmarks should have a unique role or role/label/title (i.e. accessible name) combination |
| region | moderate | - | 25 | 0 | S1, S2, S3 | All page content should be contained by landmarks |

## Every issue

| # | Screen | Rule | Impact | Element | Found by |
|---|---|---|---|---|---|
| 1 | S1-order-detail | image-alt | critical | `.navbar-brand > img` | axe+lighthouse |
| 2 | S2-mark-paid-form | image-alt | critical | `.navbar-brand > img` | axe+lighthouse |
| 3 | S3-cancel-form | image-alt | critical | `.navbar-brand > img` | axe+lighthouse |
| 4 | S1-order-detail | color-contrast | serious | `.context-meta` | axe+lighthouse |
| 5 | S1-order-detail | color-contrast | serious | `.items.panel-default.panel > .panel-heading > .pull-right.flip > a:nth-child(1)` | axe+lighthouse |
| 6 | S1-order-detail | color-contrast | serious | `.pull-right.flip > a:nth-child(2)` | axe+lighthouse |
| 7 | S1-order-detail | color-contrast | serious | `.col-md-6:nth-child(1) > .panel-default.panel > .panel-heading > .pull-right.flip > a` | axe+lighthouse |
| 8 | S2-mark-paid-form | color-contrast | serious | `.context-meta` | axe+lighthouse |
| 9 | S3-cancel-form | color-contrast | serious | `.context-meta` | axe+lighthouse |
| 10 | S1-order-detail | html-has-lang | serious | `html` | axe+lighthouse |
| 11 | S2-mark-paid-form | html-has-lang | serious | `html` | axe+lighthouse |
| 12 | S3-cancel-form | html-has-lang | serious | `html` | axe+lighthouse |
| 13 | S1-order-detail | link-in-text-block | serious | `a[rel="noopener"]` | axe+lighthouse |
| 14 | S2-mark-paid-form | link-in-text-block | serious | `a[rel="noopener"]` | axe+lighthouse |
| 15 | S3-cancel-form | link-in-text-block | serious | `a[rel="noopener"]` | axe+lighthouse |
| 16 | S1-order-detail | link-name | serious | `li:nth-child(2) > .arrow[href="#"]` | axe+lighthouse |
| 17 | S1-order-detail | link-name | serious | `.active > .arrow[href="#"]` | axe+lighthouse |
| 18 | S1-order-detail | link-name | serious | `li:nth-child(4) > .arrow[href="#"]` | axe+lighthouse |
| 19 | S1-order-detail | link-name | serious | `dd:nth-child(8) > .btn-xs.btn.btn-default` | axe+lighthouse |
| 20 | S1-order-detail | link-name | serious | `dd:nth-child(10) > .btn-xs.btn.btn-default:nth-child(1)` | axe+lighthouse |
| 21 | S1-order-detail | link-name | serious | `dd:nth-child(10) > .btn-xs.btn.btn-default:nth-child(2)` | axe+lighthouse |
| 22 | S2-mark-paid-form | link-name | serious | `li:nth-child(2) > .arrow[href="#"]` | axe+lighthouse |
| 23 | S2-mark-paid-form | link-name | serious | `.active > .arrow[href="#"]` | axe+lighthouse |
| 24 | S2-mark-paid-form | link-name | serious | `li:nth-child(4) > .arrow[href="#"]` | axe+lighthouse |
| 25 | S3-cancel-form | link-name | serious | `li:nth-child(2) > .arrow[href="#"]` | axe+lighthouse |
| 26 | S3-cancel-form | link-name | serious | `.active > .arrow[href="#"]` | axe+lighthouse |
| 27 | S3-cancel-form | link-name | serious | `li:nth-child(4) > .arrow[href="#"]` | axe+lighthouse |
| 28 | S1-order-detail | heading-order | moderate | `.panel-primary > .panel-heading > h3` | axe+lighthouse |
| 29 | S1-order-detail | landmark-one-main | moderate | `html` | axe+lighthouse |
| 30 | S2-mark-paid-form | landmark-one-main | moderate | `html` | axe+lighthouse |
| 31 | S3-cancel-form | landmark-one-main | moderate | `html` | axe+lighthouse |
| 32 | S1-order-detail | landmark-unique | moderate | `nav` | axe |
| 33 | S2-mark-paid-form | landmark-unique | moderate | `nav` | axe |
| 34 | S3-cancel-form | landmark-unique | moderate | `nav` | axe |
| 35 | S1-order-detail | region | moderate | `h1` | axe |
| 36 | S1-order-detail | region | moderate | `.btn-toolbar` | axe |
| 37 | S1-order-detail | region | moderate | `.panel-primary` | axe |
| 38 | S1-order-detail | region | moderate | `.col-lg-10 > .items.panel-default.panel` | axe |
| 39 | S1-order-detail | region | moderate | `.payments` | axe |
| 40 | S1-order-detail | region | moderate | `.col-md-6:nth-child(1)` | axe |
| 41 | S1-order-detail | region | moderate | `.col-md-6:nth-child(2) > .items.panel-default.panel > .panel-heading` | axe |
| 42 | S1-order-detail | region | moderate | `.form-group:nth-child(2)` | axe |
| 43 | S1-order-detail | region | moderate | `.form-group:nth-child(3)` | axe |
| 44 | S1-order-detail | region | moderate | `.form-group:nth-child(4)` | axe |
| 45 | S1-order-detail | region | moderate | `.form-group:nth-child(5)` | axe |
| 46 | S1-order-detail | region | moderate | `.col-lg-2` | axe |
| 47 | S2-mark-paid-form | region | moderate | `h1` | axe |
| 48 | S2-mark-paid-form | region | moderate | `form[method="post"] > p` | axe |
| 49 | S2-mark-paid-form | region | moderate | `.form-group:nth-child(4)` | axe |
| 50 | S2-mark-paid-form | region | moderate | `.form-group:nth-child(5)` | axe |
| 51 | S2-mark-paid-form | region | moderate | `.form-group:nth-child(6)` | axe |
| 52 | S2-mark-paid-form | region | moderate | `.btn-default` | axe |
| 53 | S3-cancel-form | region | moderate | `h1` | axe |
| 54 | S3-cancel-form | region | moderate | `.container-fluid > p:nth-child(2)` | axe |
| 55 | S3-cancel-form | region | moderate | `.container-fluid > p:nth-child(3)` | axe |
| 56 | S3-cancel-form | region | moderate | `.form-group:nth-child(3)` | axe |
| 57 | S3-cancel-form | region | moderate | `.form-group:nth-child(4)` | axe |
| 58 | S3-cancel-form | region | moderate | `.form-group:nth-child(5)` | axe |
| 59 | S3-cancel-form | region | moderate | `.col-md-4:nth-child(1)` | axe |

## Page-level Lighthouse audits (best practices, SEO)

| Screen | Category | Audit | Problem |
|---|---|---|---|
| S1-order-detail | best-practices | valid-source-maps | Missing source maps for large first-party JavaScript |
| S1-order-detail | seo | is-crawlable | Page is blocked from indexing |
| S1-order-detail | seo | meta-description | Document does not have a meta description |
| S1-order-detail | seo | image-alt | Image elements do not have `[alt]` attributes |
| S2-mark-paid-form | best-practices | valid-source-maps | Missing source maps for large first-party JavaScript |
| S2-mark-paid-form | seo | is-crawlable | Page is blocked from indexing |
| S2-mark-paid-form | seo | meta-description | Document does not have a meta description |
| S2-mark-paid-form | seo | image-alt | Image elements do not have `[alt]` attributes |
| S3-cancel-form | best-practices | valid-source-maps | Missing source maps for large first-party JavaScript |
| S3-cancel-form | seo | is-crawlable | Page is blocked from indexing |
| S3-cancel-form | seo | meta-description | Document does not have a meta description |
| S3-cancel-form | seo | image-alt | Image elements do not have `[alt]` attributes |
