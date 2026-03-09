# 🚀 Prototype Link & Deployment Guide

This guide covers how to generate a temporary prototype link immediately, how to push your project repository to GitHub, and how to permanently deploy it on a platform like Render.

---

## 1. Instant Prototype Link (Temporary)

You can get a public link to your app quickly without deploying it to a third-party server.

**Option A: Using Serveo (No installation required)**
1. Ensure your local app is running (double-click `start.bat`).
2. Open PowerShell or Command Prompt.
3. Run this command:
   ```bash
   ssh -R 80:localhost:5000 serveo.net
   ```
4. It will print a public URL (e.g., `https://alien.serveo.net`) that you can share immediately. Note: This link only works while your computer is on and the app is running.

**Option B: Using Ngrok**
1. Download and install [Ngrok](https://ngrok.com/).
2. Start your app.
3. Run `ngrok http 5000` in your terminal to get your temporary secure link.

---

## 2. GitHub Repository Setup

Your local folder has already been formatted as a complete Git repository with an initial commit! To complete the requirement of "giving the repo of this project," follow these steps:

1. Go to [GitHub.com](https://github.com/new) and log in.
2. Create a **New Repository** (do NOT initialize it with a README, .gitignore, or license).
3. Once created, copy the repository URL (e.g., `https://github.com/YourUsername/ai-video-studio.git`).
4. Open your terminal in the project folder and run:
   ```bash
   git remote add origin <paste-your-repo-url-here>
   git branch -M main
   git push -u origin main
   ```
Your code is now on GitHub! You can share this repository link.

---

## 3. Permanent Deployment on a Third-Party App (Render)

If you want a permanent prototype link that doesn't rely on your computer, [Render](https://render.com/) is a great free option. I've already prepared the necessary `Procfile` and `requirements.txt` for you.

1. Sign up for [Render.com](https://render.com/) using your GitHub account.
2. Click **New +** and select **Web Service**.
3. Connect your GitHub account and select the repository you just pushed.
4. Render will auto-detect the settings. Ensure they look like this:
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app` (This uses the `Procfile` I created).
5. **Critical**: Scroll down to **Environment Variables** and add:
   - **Key:** `GEMINI_API_KEY`
   - **Value:** `<Your Gemini API Key>`
6. Click **Create Web Service**. 

Once the build finishes (about 2-3 minutes), Render will give you a permanent `.onrender.com` link to share!
