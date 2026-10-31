# Security policy

Please **do not open a public issue** for security problems. Report them privately through GitHub's **Security → Report a vulnerability** on this repository. You'll get an acknowledgement within a few days.

When self-hosting:

- Use a long random `SECRET_KEY` (the app refuses placeholders in production) and keep it identical on every host that runs the code.
- Keep `ALLOW_REGISTRATION=false` and add people through invites.
- Never commit `.env`. Rotate any credential that ends up in git history.
- Profiles, resumes and applications are personal data. Run your instance as invite-only.
