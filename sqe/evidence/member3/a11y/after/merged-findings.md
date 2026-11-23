# Accessibility findings (after)

7 unique element-level issues across 1 screens; 7 were found by both tools and are counted once.

## By rule

| Rule | Impact | WCAG | Issues | Found by both | Screens | Problem |
|---|---|---|---|---|---|---|
| color-contrast | serious | wcag2aa wcag143 | 3 | 3 | S1 | Elements must meet minimum color contrast ratio thresholds |
| link-name | serious | wcag2a wcag244 wcag412 | 3 | 3 | S1 | Links must have discernible text |
| heading-order | moderate | - | 1 | 1 | S1 | Heading levels should only increase by one |

## Every issue

| # | Screen | Rule | Impact | Element | Found by |
|---|---|---|---|---|---|
| 1 | S1-order-detail | color-contrast | serious | `.items.panel-default.panel > .panel-heading > .pull-right.flip > a:nth-child(1)` | axe+lighthouse |
| 2 | S1-order-detail | color-contrast | serious | `.pull-right.flip > a:nth-child(2)` | axe+lighthouse |
| 3 | S1-order-detail | color-contrast | serious | `.col-md-6:nth-child(1) > .panel-default.panel > .panel-heading > .pull-right.flip > a` | axe+lighthouse |
| 4 | S1-order-detail | link-name | serious | `dd:nth-child(8) > .btn-xs.btn.btn-default` | axe+lighthouse |
| 5 | S1-order-detail | link-name | serious | `dd:nth-child(10) > .btn-xs.btn.btn-default:nth-child(1)` | axe+lighthouse |
| 6 | S1-order-detail | link-name | serious | `dd:nth-child(10) > .btn-xs.btn.btn-default:nth-child(2)` | axe+lighthouse |
| 7 | S1-order-detail | heading-order | moderate | `.panel-primary > .panel-heading > h3` | axe+lighthouse |

## Page-level Lighthouse audits (best practices, SEO)

| Screen | Category | Audit | Problem |
|---|---|---|---|
| S1-order-detail | best-practices | valid-source-maps | Missing source maps for large first-party JavaScript |
| S1-order-detail | seo | is-crawlable | Page is blocked from indexing |
| S1-order-detail | seo | meta-description | Document does not have a meta description |
| S2-mark-paid-form | best-practices | valid-source-maps | Missing source maps for large first-party JavaScript |
| S2-mark-paid-form | seo | is-crawlable | Page is blocked from indexing |
| S2-mark-paid-form | seo | meta-description | Document does not have a meta description |
| S3-cancel-form | best-practices | valid-source-maps | Missing source maps for large first-party JavaScript |
| S3-cancel-form | seo | is-crawlable | Page is blocked from indexing |
| S3-cancel-form | seo | meta-description | Document does not have a meta description |
