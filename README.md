<p align="center">
  <img alt="GitHub closed issues" src="https://raw.githubusercontent.com/suitenumerique/dictaphone/refs/heads/main/src/frontend/public/assets/logo-single-line.svg"/>
</p>

<p align="center">
  <a href="https://github.com/suitenumerique/dictaphone/stargazers/">
    <img src="https://img.shields.io/github/stars/suitenumerique/dictaphone" alt="">
  </a>
  <img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/suitenumerique/dictaphone"/>
  <img alt="GitHub closed issues" src="https://img.shields.io/github/issues-closed/suitenumerique/dictaphone"/>
  <a href="https://github.com/suitenumerique/dictaphone/blob/main/LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/suitenumerique/dictaphone"/>
  </a>
</p>

<p align="center">
  <a href="https://github.com/suitenumerique/dictaphone/blob/main/CHANGELOG.md">Changelog</a>
  ·
  <a href="https://github.com/suitenumerique/dictaphone/issues/new?assignees=&labels=bug&template=Bug_report.md">Bug reports</a>
</p>

# Assistant Transcripts (Dictaphone)

This repository is the source code for **Assistant Transcripts** — a transcription and meeting workflow product aimed at teams in the French public sector (central administrations and supervised bodies). It helps agents collaborate around recordings and meetings.

- **Public web application:** [transcripts.numerique.gouv.fr](https://transcripts.numerique.gouv.fr/)
- [**iOS Application**](https://apps.apple.com/fr/app/assistant-transcripts/id6762260492)
- [**Android Application**](https://play.google.com/store/apps/details?id=fr.gouv.assistant_transcripts)

Assistant Transcripts is developed and operated by **DINUM** ([Direction interministérielle du numérique](https://www.numerique.gouv.fr/)), as part of the broader **La Suite numérique** ecosystem.

_NB: The project codename and Python package name remain **Dictaphone**; GitHub and CI refer to this repo as `dictaphone`._

## What ships in this repo

| Components | Stack / notes                                                                                |
| ---------- | -------------------------------------------------------------------------------------------- |
| Backend    | Python, Django, Celery under [`src/backend/`](./src/backend/) <br> _PostgreSQL / Redis / S3_ |
| Web App    | React SPA, Vite under [`src/frontend/`](./src/frontend/)                                         |
| Mobile App | React Native app under [`src/mobile/`](./src/mobile/)                                        |
| Helm Chart | Under [`src/helm/`](./src/helm/)                                                             |

Note that the main processing pipeline is currently hosted under [La Suite Meet repository](https://github.com/suitenumerique/meet), under the [summary component](https://github.com/suitenumerique/meet/tree/main/src/summary). It is based on WhisperX.

## Self-host

We use Kubernetes for our [production instance](https://transcripts.numerique.gouv.fr/) but also support Docker Compose. The complexity comes mostly from deploying the _summary_ component / WhisperX.

> [!NOTE]
> We are working hard to simplify and document the installation process. We will update this page as soon as possible.

## Getting started (developers)

See **[Developing locally](./docs/developping_locally.md)** for Docker Compose or Kubernetes/Tilt (recommended). Run `make help` for Make targets.

## Contributing

Contributions are welcome.

<!-- - Roadmap and prioritisation: [Suite Numérique project board](https://github.com/orgs/suitenumerique/projects/11/views/4) -->

- Open a PR following [local development](./docs/developping_locally.md)
- [Feature request](https://github.com/suitenumerique/dictaphone/issues/new?assignees=&labels=enhancement&template=Feature_request.md) · [Bug report](https://github.com/suitenumerique/dictaphone/issues/new?assignees=&labels=bug&template=Bug_report.md)

Security disclosures: please use the [French administration vulnerability disclosure programme](https://vdp.numerique.gouv.fr/) rather than public GitHub issues. General contact: [<support-transcripts@numerique.gouv.fr>
](mailto:<support-transcripts@numerique.gouv.fr>).

## Open-source

Gov 🇫🇷 supports open source! This project is available under [MIT license](./LICENSE.md).

All features we develop will always remain open-source, and we are committed to contributing back to the community whenever feasible.

## Contributors

<a href="https://github.com/suitenumerique/dictaphone/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=suitenumerique/dictaphone" alt="Contributors" />
</a>

## Credits

A special thanks to the teams behind [Django REST framework](https://www.django-rest-framework.org/) and [Vite](https://vite.dev/) among other amazing open source projects we rely on.

# License

Code in this repository is published under the MIT license by DINUM (Direction interministérielle du numérique).

Documentation under `docs/` is released under the [Etalab 2.0 license](https://spdx.org/licenses/etalab-2.0.html).
