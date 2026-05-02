"""Schemas for host Docker maintenance and stack deploy from the panel."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DockerPrunePreset = Literal["light", "deep"]

StackDeployMode = Literal["frontend", "frontend_backend", "rebuild_app", "full"]


class DockerPruneRequest(BaseModel):
    preset: DockerPrunePreset = "deep"


class StackDeployRequest(BaseModel):
    mode: StackDeployMode = Field(description="frontend | frontend_backend | rebuild_app | full")


class HostOpsScheduleIn(BaseModel):
    enabled: bool = False
    preset: DockerPrunePreset = "deep"
    hour: int = Field(ge=0, le=23, default=4)
    minute: int = Field(ge=0, le=59, default=10)
    """0=domingo … 6=sábado. null = todos los días."""
    dow: int | None = Field(default=None, ge=0, le=6)


class HostOpsConfigOut(BaseModel):
    docker_control_enabled: bool
    stack_deploy_enabled: bool
    docker_socket_present: bool
    stack_path_configured: bool
    compose_dir: str | None
    runner_image_configured: bool = False
    schedule: dict
