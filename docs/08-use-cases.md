# 8. Use Cases

## Actors

| Actor | Who |
|-------|-----|
| **Visitor** | A business owner who wants to check their website |
| **Consultant** | The person in `branding.yaml`, who uses the report to win clients |

## Use case 1: Check a website

1. The visitor opens BizzCheckup and enters their website address.
2. BizzCheckup scans the site:
   - It asks Google PageSpeed Insights for performance, accessibility, best-practices and
     SEO scores.
   - It runs its own checks for AI-readiness (`llms.txt`, AI crawler rules in
     `robots.txt`, structured data) and security headers.
3. The visitor sees the Health Report in the browser.

## Use case 2: Download the report as PDF

1. On the report page, the visitor clicks **Download PDF**.
2. They get a PDF with the same design as the web page: cover, scores, problems found,
   recommended services, and contact page.

## Use case 3: Get recommended services

For each category that scores low, the report shows the matching services from
`branding.yaml` (through `related_categories`) and a call to action to book a free review
call.

## Use case 4: Rebrand (for forks)

Someone else copies the project and edits only `branding.yaml`. All reports then show
their name, services and contact details.

> More use cases (scan history, admin dashboard, email delivery) are added here when
> built.
