# Family Genealogy Tool Lite - Static Version

This is a static, read-only version of the Family Genealogy Tool that can be hosted on GitHub Pages.

## Overview

This version loads genealogy data from JSON files instead of querying a database, making it suitable for static hosting platforms like GitHub Pages.

## Structure

```
docs/
├── index.html              # Main entry point (people list)
├── tree.html              # Tree visualization (if created)
├── analytics.html         # Analytics dashboard (if created)
├── data/                  # JSON data files
│   ├── persons.json       # All persons in the family tree
│   ├── families.json      # Family units
│   ├── family_children.json # Parent-child relationships via families
│   ├── relationships.json  # Direct parent-child relationships
│   ├── events.json        # Life events
│   ├── places.json        # Canonical places
│   ├── place_variants.json # Place name variants
│   ├── media_assets.json  # Media files metadata
│   ├── media_links.json   # Links between media and people/families
│   ├── notes.json         # Notes attached to persons/families
│   └── _metadata.json     # Export metadata
└── static/                # Static assets
    ├── data-adapter.js    # Data loading layer for JSON files
    ├── app-static.js      # Modified app logic for static version
    ├── styles.css         # Stylesheets
    ├── help.js           # Help system
    └── icons/            # App icons

```

## Features

- **Read-only view**: Browse all persons in the genealogy database
- **Search**: Filter persons by name
- **Details view**: View person details including birth/death information
- **Mini tree**: See immediate family connections (parents and children)
- **Notes**: View notes attached to persons
- **Media**: See media associated with persons

## Limitations

This static version has some limitations compared to the full Flask application:

- **Read-only**: Cannot add, edit, or delete persons
- **No import**: Cannot import GEDCOM or RMTree files
- **No media upload**: Cannot upload new media files
- **No data quality tools**: Analytics and data quality features are simplified
- **Static data**: Data must be re-exported from the database to update the site

## Updating the Data

To update the JSON files with new data from the Family Genealogy Tool database:

1. Make sure you have the Family Genealogy Tool running locally
2. Import or update your genealogy data in the tool
3. Run the export script:
   ```bash
   python3 scripts/export_to_json.py
   ```
4. Commit and push the updated JSON files to GitHub
5. GitHub Pages will automatically update the site

## Deployment to GitHub Pages

1. Enable GitHub Pages in your repository settings
2. Set the source to the `docs` folder (or `gh-pages` branch if you prefer)
3. Your site will be available at `https://<username>.github.io/<repository>/`

## Browser Compatibility

This static version uses modern JavaScript features and requires a recent browser:

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari 14+, Chrome Android 90+)

## License

Same as the main Family Genealogy Tool Lite project.
