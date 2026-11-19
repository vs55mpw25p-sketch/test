# Filmspuren video extractor

Authenticated server-side frame extraction for public Internet Archive videos. This repository contains service code only: no private research database or credentials.

## Run

Build the Dockerfile. Configure VIDEO_EXTRACTOR_TOKEN with a cryptographically random secret of at least 32 characters using the hosting secret settings. Never commit it. PORT defaults to 8080.

GET /health returns a health status. POST /extract requires Authorization: Bearer followed by the shared secret, and JSON containing url and time (seconds).

The response contains a JPEG data URL, timestamp, duration, three perceptual hashes (original, mirrored, cropped), image variance and the downloaded file SHA-256. A timestamp beyond the end returns eof.

## Limits

Only direct HTTPS archive.org/download/ MP4 or WebM links are accepted. Redirects are restricted to public archive.org hosts. Maximum file size is 150 MiB; downloads and extraction have timeouts. One extraction runs at a time. A temporary one-file cache expires after an hour and can disappear on redeployment.

This service does not schedule jobs, keep permanent progress, describe scenes with AI, or establish footage identity. The calling application must persist its queue, images and cursor and retry failures. Perceptual hashes are evidence for review, not proof of duplication. Public availability is not permission to republish.

## Validation

Validated locally with a synthetic video: frame extraction, end-of-file, URL rejection, health response and rejection of unauthenticated extraction. A deployed real-video test is still required.
