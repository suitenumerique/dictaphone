# Getting Started

Before setting up, let's review Dictaphone's architecture.

Dictaphone consists of 3 main components that run simultaneously:

- React frontend, built with Vite.js
- Django server
- A FastAPI server, that handles the transcription -- currently under [La Suite Meet repository](https://github.com/suitenumerique/meet), known as the [summary component](https://github.com/suitenumerique/meet/tree/main/src/summary).

These components rely on a few key services:

- PostgreSQL for storing data (users, recordings, AI jobs results)
- Redis for caching and inter-service communication
- MinIO for storing files (room recordings)
- Celery workers to handle async jobs

We provide two stack options for getting Dictaphone up and running for development:

- Docker Compose stack
- Kubernetes stack powered by Tilt (recommended, as it ease setup with the summary component)

We recommend starting with the **Tilt** option for simplicity, which is the only one tested currently with all the functionnalities.

These instructions are for macOS or Ubuntu. For other distros, adjust as needed.

If any steps are outdated, please let us know!

---

We also provide **GNU make utilities**. To view all available Make rules, run:

```shellscript
$ make help
```

---

## Need Help?

If you need any assistance or have questions while getting started, feel free to reach out to @flochehab anytime! Flo is available to help you onboard and guide you through the process.

---

## Option 1: Developing with Docker

### Prerequisites

1. Ensure you have a recent version of **Docker** and **Docker Compose** installed:

```shellscript
$ docker -v
Docker version 29.4.3, build 055a478

$ docker compose version
Docker Compose version v5.1.3
```

---

### Project Bootstrap

1. Bootstrap the project using the **Make** command. This will build the `app` container, install dependencies, run database migrations, and compile translations:

```shellscript
make bootstrap FLUSH_ARGS='--no-input'
```

2. Access the project:

- The frontend is available at [http://localhost:3000](http://localhost:3000) with the default credentials:
  - username: dictaphone
  - password: dictaphone
- The Django backend is available at [http://localhost:8071](http://localhost:8071)
- The Django admin is available at [http://localhost:8071/admin](http://localhost:8071/admin)
  - username: admin@example.com
  - password: admin

---

## Developing

- To **stop** the application:

```shellscript
make stop
```

- To **restart** the application:

```shellscript
make run
```

- For **frontend development**, start all backend services without the frontend container:

```shellscript
make run-backend
```

Then:

```shellscript
make frontend-development-install
make run-frontend-development
```

Which is equivalent to these direct npm commands:

```shellscript
cd src/frontend
npm i
npm run dev
```

---

## Adding Content

You can bootstrap demo data with a single command:

```shellscript
make demo
```

---

## Option 2: Developing with Kubernetes

Dictaphone is deployed across staging, preprod, and production environments using **Kubernetes (K8s)**. Reproducing the environment locally is crucial for developing new features or debugging.

This is facilitated by [Tilt](https://tilt.dev/), which provides Kubernetes-like development for local environments, enabling smart rebuilds and live updates.

### Getting Started

Make sure you have the following installed:

- kubectl
- helm
- helmfile
- tilt

To build and start the Kubernetes cluster using **Kind**:

```shellscript
make build-k8s-cluster
```

Once the Kubernetes cluster is ready, start the application stack locally:

```shellscript
make start-tilt-keycloak
```

Monitor Tilt’s progress at [http://localhost:10350/](http://localhost:10350/). After Tilt actions finish, you can access the app at [https://dictaphone.127.0.0.1.nip.io/](https://dictaphone.127.0.0.1.nip.io/).

### Connecting the Summary component

To easily connect the summary component, clone the Meet repo and start tilt there (on another port).

```bash
git clone https://github.com/suitenumerique/meet.git
make env.d/development/kube-secret
# Make sure to configure the variables in env.d/development/kube-secret file
vim env.d/development/kube-secret
# This will start a full visio instance, with the summary component.
# We are working on extracting the summary component from that stack as soon as possible.
TILT_PORT=10351 make start-tilt-keycloak
```

Once both tilt are up and running (start the dictaphone one first), you should be able to test the functionalities end to end (except the docs-related features).

# Developing the mobile app

For now it's easier to develop the mobile app against a fully deployed backend either in pre-prod or in prod, by tweaking the API url in [constants.ts](../src/mobile/src/api/constants.ts).

Follow the [Mobile Readme](../src/mobile/README.md) to get started on tweaking the mobile app.
