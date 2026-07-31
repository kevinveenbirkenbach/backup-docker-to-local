"""Which volumes are backed up, and which containers must stop for it."""

from __future__ import annotations

from .docker import get_image_info, is_swarm_task


def is_image_ignored(container: str, images_no_backup_required: list[str]) -> bool:
    if not images_no_backup_required:
        return False
    img = get_image_info(container)
    return img in images_no_backup_required


def volume_is_fully_ignored(
    containers: list[str], images_no_backup_required: list[str]
) -> bool:
    """
    Skip file backup only if all containers linked to the volume are ignored.
    """
    if not containers:
        return False
    return all(is_image_ignored(c, images_no_backup_required) for c in containers)


def requires_stop(containers: list[str], images_no_stop_required: list[str]) -> bool:
    """
    Stop is required if ANY stoppable container image is NOT in the exact
    image whitelist. Swarm task containers never count: baudolo must
    not cycle them (see docker.is_swarm_task).
    """
    for c in containers:
        if is_swarm_task(c):
            continue
        img = get_image_info(c)
        if img not in images_no_stop_required:
            return True
    return False
