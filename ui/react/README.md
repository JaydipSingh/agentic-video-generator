# React UI for Agentic Video Generator

Modern React-based frontend for the Agentic Video Generator, featuring form submission, real-time status polling, and video preview.

## Features

- **Job Submission**: Fill out form with story, style, duration, aspect ratio, FPS, and voiceover settings
- **Real-time Status Polling**: Auto-refresh job status with configurable polling interval
- **Resume Failed Jobs**: Checkpoint-aware resume for failed generations
- **Video Preview**: Embedded video player for completed jobs
- **Responsive Design**: Mobile-friendly layout with Tailwind CSS
- **Dark Theme**: Modern dark UI with gradient backgrounds

## Installation

```bash
cd ui/react
npm install
```

## Configuration

Set the API backend URL via environment variable:

```bash
REACT_APP_API_BASE_URL=http://127.0.0.1:8000 npm start
```

Or update the default in the app (currently `http://127.0.0.1:8000`).

## Running the App

```bash
npm start
```

The app opens at `http://localhost:3000`

## Build for Production

```bash
npm run build
```

Output is in the `build/` directory.

## API Endpoints Used

- `POST /generate` - Submit new video generation request
- `GET /jobs/{job_id}` - Fetch job status and progress
- `POST /jobs/{job_id}/resume` - Resume a failed job

## Technologies

- **React 18**: UI framework
- **Axios**: HTTP client for API calls
- **Tailwind CSS**: Utility-first CSS framework
- **React Scripts**: Build tooling

## Comparison with Streamlit UI

| Feature | Streamlit | React |
|---------|-----------|-------|
| Form Submission | ✓ | ✓ |
| Real-time Polling | ✓ | ✓ |
| Resume Jobs | ✓ | ✓ |
| Video Preview | ✓ | ✓ |
| Responsive Design | Limited | ✓ Full |
| Dark Theme | ✓ | ✓ Modern |
| Customization | Limited | ✓ Full |
| Hosting | Streamlit Cloud | Any static host |

## Future Enhancements

- [ ] Job history/dashboard
- [ ] Advanced filtering and search
- [ ] Batch job submission
- [ ] Real-time WebSocket updates
- [ ] Provider credential management UI
- [ ] Job analytics and metrics
