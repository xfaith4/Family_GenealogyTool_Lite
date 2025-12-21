# Deploying to GitHub Pages

This guide explains how to deploy your Family Genealogy Tool to GitHub Pages.

## Quick Start

1. **Enable GitHub Pages** in your repository:
   - Go to Settings → Pages
   - Source: Deploy from a branch
   - Branch: Select `main` (or your default branch) and `/docs` folder
   - Click Save

2. **Your site will be live at:**
   ```
   https://[username].github.io/[repository-name]/
   ```

That's it! GitHub will automatically build and deploy your site.

## Updating Your Data

When you add or modify genealogy data, you need to re-export the JSON files:

### Option 1: Using the Update Script (Recommended)

```bash
python3 scripts/update_static_site.py
git add docs/data/*.json
git commit -m "Update genealogy data"
git push
```

### Option 2: Manual Export

```bash
python3 scripts/export_to_json.py
git add docs/data/*.json
git commit -m "Update genealogy data"
git push
```

GitHub Pages will automatically update your site within a few minutes.

## Workflow

### Initial Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Start the app: `python run.py`
4. Import your GEDCOM or RMTree data
5. Export to JSON: `python3 scripts/export_to_json.py`
6. Commit and push the docs folder

### Regular Updates

1. Start the app: `python run.py`
2. Make changes (add people, import new data, etc.)
3. Export to JSON: `python3 scripts/update_static_site.py`
4. Commit and push changes

## File Structure

```
docs/
├── index.html              # Main page - people list
├── tree.html              # Tree view - organized by surname
├── analytics.html         # Analytics dashboard
├── .nojekyll             # Tells GitHub Pages to serve all files
├── data/                  # JSON data files
│   ├── persons.json       # All persons
│   ├── families.json      # Family units
│   ├── relationships.json # Parent-child relationships
│   └── ...               # Other data tables
└── static/               # Static assets
    ├── data-adapter.js    # Loads JSON files
    ├── app-static.js      # Main app logic
    ├── styles.css         # Styles
    └── ...               # Other assets
```

## Custom Domain (Optional)

To use a custom domain:

1. Add a `CNAME` file to the `docs/` folder:
   ```
   yourdomain.com
   ```

2. Configure your DNS provider:
   - Add a CNAME record pointing to `[username].github.io`
   - Or add A records pointing to GitHub's IPs

3. In GitHub Settings → Pages, enter your custom domain

See [GitHub's documentation](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site) for details.

## Troubleshooting

### Site not updating

- Check the Actions tab in GitHub to see if the deployment succeeded
- Make sure you committed and pushed the `docs/data/*.json` files
- Wait a few minutes - deployments can take 5-10 minutes

### 404 errors

- Make sure GitHub Pages is pointing to the `/docs` folder
- Check that `.nojekyll` file exists in the docs folder
- Verify all files are committed and pushed

### JavaScript not loading data

- Open browser console (F12) and check for errors
- Verify JSON files are accessible: `https://[your-site]/data/persons.json`
- Check that the data files are not empty

### CSS not loading

- Verify all paths in HTML files use relative paths (`./static/` not `/static/`)
- Check that static files are committed in the docs folder

## Privacy Considerations

**Important:** GitHub Pages sites are **public by default**. Anyone with the URL can access your family tree data.

### Options for Privacy

1. **Private Repository** (requires GitHub Pro/Team):
   - Make your repository private
   - GitHub Pages will still work but only for authenticated users

2. **Password Protection**:
   - Add basic authentication (requires additional setup)
   - Use a third-party service like Netlify with password protection

3. **Limit Data**:
   - Only export data you're comfortable sharing publicly
   - Remove sensitive information before exporting

4. **Self-Host**:
   - Use the full Flask app on a private server
   - Deploy to a platform with built-in authentication

## Performance

The static site loads all data client-side. Performance considerations:

- **Small datasets (< 1000 persons)**: Excellent performance
- **Medium datasets (1000-5000 persons)**: Good performance on modern devices
- **Large datasets (> 5000 persons)**: May be slow on older devices

For large datasets, consider:
- Splitting data into multiple files
- Implementing pagination
- Using the full Flask app instead

## Maintenance

The static site requires minimal maintenance:

- **Update data**: Run export script when data changes
- **Update style/features**: Edit files in docs/ folder
- **Keep dependencies updated**: The site has no runtime dependencies

## Support

For issues or questions:
- Check the main README.md
- Review this guide
- Open an issue on GitHub
