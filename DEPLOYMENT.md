# Deployment Guide: Lectionary Engines

## Quick Deploy Options

### Option 1: Railway (Recommended)

**Pros:** Fastest setup, automatic HTTPS, generous free tier
**Time:** 5 minutes

1. **Push latest code to GitHub:**
   ```bash
   git add .
   git commit -m "Add deployment configuration"
   git push
   ```

2. **Deploy to Railway:**
   - Visit https://railway.app/
   - Sign up with GitHub
   - Click "New Project" → "Deploy from GitHub repo"
   - Select `lectionary-engines` repository
   - Railway auto-detects Python and deploys

3. **Configure Environment Variables:**
   - In Railway dashboard, go to your project → Variables
   - Add: `ANTHROPIC_API_KEY` = `your-api-key-here`
   - Railway will automatically redeploy

4. **Get your URL:**
   - Click "Settings" → "Domains"
   - Generate a domain (e.g., `lectionary-engines.up.railway.app`)
   - Or add custom domain

5. **Initialize Database:**
   - Once deployed, run migration via Railway console:
   ```bash
   python web/migrations/001_add_user_profiles.py
   ```
   - Or the database will auto-initialize on first request

---

### Option 2: Render (Free Tier)

**Pros:** Free tier available, easy to use
**Time:** 10 minutes

1. **Push code to GitHub** (if not already done)

2. **Deploy to Render:**
   - Visit https://render.com/
   - Sign up with GitHub
   - Click "New" → "Web Service"
   - Connect your `lectionary-engines` repo
   - Select branch: `main`
   - Render will auto-detect `render.yaml`

3. **Configure Environment:**
   - Add environment variable:
     - Key: `ANTHROPIC_API_KEY`
     - Value: Your API key
   - Free tier: Instance will spin down after inactivity

4. **Get your URL:**
   - Render provides: `https://your-app.onrender.com`
   - Can add custom domain in settings

---

### Option 3: Heroku

**Note:** Heroku no longer has a free tier, but offers low-cost options

1. **Install Heroku CLI** (if needed):
   ```bash
   brew install heroku/brew/heroku
   ```

2. **Login and create app:**
   ```bash
   heroku login
   heroku create lectionary-engines
   ```

3. **Set environment variables:**
   ```bash
   heroku config:set ANTHROPIC_API_KEY=your-api-key-here
   ```

4. **Deploy:**
   ```bash
   git push heroku main
   ```

5. **Initialize database:**
   ```bash
   heroku run python web/migrations/001_add_user_profiles.py
   ```

---

## Post-Deployment Checklist

- [ ] Application is accessible at your deployment URL
- [ ] API key is configured (test by generating a study)
- [ ] Database migration has run (check /api/profiles returns 5 profiles)
- [ ] All 5 user profiles are present
- [ ] Can generate studies with different profiles
- [ ] Studies are saved to database

---

## Integrating with Squarespace

Once deployed, you have three options for integrating with Squarespace:

### Option 1: Embedded iframe (Seamless Integration)

1. In Squarespace, add a **Code Block** to your page
2. Insert this HTML:
   ```html
   <div style="width: 100%; height: 100vh; min-height: 800px;">
     <iframe
       src="https://your-app.railway.app/generate"
       style="width: 100%; height: 100%; border: none;"
       title="Lectionary Engines Study Generator">
     </iframe>
   </div>
   ```

3. Adjust `height` as needed for your design

**Pros:** Feels like part of your site
**Cons:** iframe limitations (scrolling, mobile experience)

---

### Option 2: Full Page Embed (Recommended)

1. Create a new **blank page** in Squarespace
2. Set page to **Full Width** in page settings
3. Add **Code Block** covering entire page:
   ```html
   <!DOCTYPE html>
   <html>
   <head>
     <style>
       body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; }
       iframe { width: 100%; height: 100%; border: none; }
     </style>
   </head>
   <body>
     <iframe src="https://your-app.railway.app/generate"></iframe>
   </body>
   </html>
   ```

4. Disable Squarespace header/footer for this page

**Pros:** Clean, full-screen experience
**Cons:** Loses Squarespace navigation

---

### Option 3: Button/Link (Simplest)

1. Add a **Button Block** in Squarespace
2. Set button text: "Generate Bible Study"
3. Link to: `https://your-app.railway.app/generate`
4. Set to open in **new tab** or **same window**

**Pros:** Simplest, most flexible
**Cons:** Takes users away from your site

---

### Option 4: Custom Domain (Most Professional)

1. **In Railway/Render:**
   - Add custom domain: `studies.yoursite.com`
   - Get CNAME record

2. **In Squarespace DNS:**
   - Add CNAME record pointing to Railway/Render

3. **Link from Squarespace:**
   - Link to `https://studies.yoursite.com`
   - Or embed via iframe

**Pros:** Professional, branded URL
**Cons:** Requires domain configuration

---

## Environment Variables

Required for deployment:

| Variable | Description | Example |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Your Claude API key | `sk-ant-...` |
| `DATABASE_URL` | Database connection (optional) | Auto-configured |
| `PORT` | Server port | Auto-configured |

Optional:

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_HOST` | `0.0.0.0` | Server host |
| `DEFAULT_TRANSLATION` | `NRSVue` | Default Bible translation |
| `STUDIES_PER_PAGE` | `20` | Pagination limit |

---

## Troubleshooting

### "Application Error" on deployment
- Check Railway/Render logs
- Verify `ANTHROPIC_API_KEY` is set
- Ensure all dependencies are in requirements files

### Database not initialized
- Run migration: `python web/migrations/001_add_user_profiles.py`
- Or visit `/api/profiles` to trigger auto-initialization

### Profiles not showing
- Check `/api/profiles` endpoint directly
- Run migration to create default profiles
- Check browser console for JavaScript errors

### CORS errors (if using subdomain)
- Add CORS middleware to `web/app.py`
- Configure allowed origins

---

## Monitoring & Maintenance

### Railway
- Dashboard shows: CPU, memory, bandwidth usage
- Logs available in real-time
- Auto-restarts on crashes

### Render
- Free tier sleeps after 15 min inactivity
- First request after sleep takes ~30 seconds
- Logs available in dashboard

### Database Backups
- SQLite database stored in project directory
- Railway: Use persistent volumes
- Render: Consider PostgreSQL for production

---

## Upgrading

To deploy new changes:

```bash
git add .
git commit -m "Description of changes"
git push
```

Railway/Render will automatically detect and redeploy.

---

## Security Considerations

- **API Key:** Never commit to git (use environment variables)
- **HTTPS:** Automatically provided by Railway/Render
- **Database:** Consider PostgreSQL for production (more robust)
- **Rate Limiting:** Add if experiencing abuse
- **Authentication:** Consider adding user accounts for production

---

## Cost Estimates

### Railway
- Free tier: $5 credit/month
- Hobby plan: $5/month (500 hours)
- Typical cost: $5-10/month for low traffic

### Render
- Free tier: Limited to 750 hours/month (sleeps after inactivity)
- Starter plan: $7/month (always-on)

### API Costs
- Claude API: ~$0.50-2.00 per study (depending on length/engine)
- Budget accordingly based on expected usage
