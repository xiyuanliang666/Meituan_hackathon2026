"""Unified prompt for AI nail try-on — works for both user try-on and merchant composite."""

from __future__ import annotations

from dataclasses import dataclass

NAIL_TRYON_PROMPT = """
You are a professional AI nail try-on image editor.

TASK:
The first image is the user's real hand photo.
The second image is the target nail design reference.

Your task is to completely replace the existing nails in image 1 with the nail design from image 2.

IMPORTANT:
The original nails in image 1 are NOT part of the target design.
They must be treated as temporary placeholder nails only.

STEP 1 — REMOVE ORIGINAL NAIL DESIGN
First, completely ignore and remove the original manicure from image 1.

Restore each fingernail to a clean natural bare nail state:
- remove original color
- remove original nail shape influence
- remove original nail length influence
- remove original gradients
- remove decorations
- remove gloss style
- remove existing acrylic/gel appearance

The original manicure in image 1 must NOT affect the final result in any way.

STEP 2 — APPLY TARGET DESIGN
Then accurately reconstruct the manicure from image 2 onto the hand in image 1.

Strictly copy from image 2:
- nail shape
- nail length
- nail thickness
- curvature
- color
- patterns
- decorations
- gloss/matte finish
- transparency
- texture
- placement of every detail

Each finger must independently match the corresponding finger design from image 2.

IMPORTANT CONSTRAINTS:
- Do NOT blend the old nails with the new nails
- Do NOT preserve any original nail color or shape
- Do NOT adapt the target design to the old manicure
- Do NOT create a hybrid manicure
- The final nails should look as if the person originally wore the manicure from image 2

HAND PRESERVATION RULE:
Except for the nail area, absolutely nothing else may change.

Preserve exactly:
- hand pose
- finger shape
- skin texture
- skin tone
- wrinkles
- lighting
- shadows
- reflections
- jewelry
- camera angle
- depth of field
- background
- image composition

Only modify the nail regions.

The final image must look photorealistic and naturally integrated.
""".strip()


@dataclass(frozen=True)
class NailTryOnPromptBundle:
    task_prompt: str


def build_try_on_prompt_bundle() -> NailTryOnPromptBundle:
    return NailTryOnPromptBundle(task_prompt=NAIL_TRYON_PROMPT)


def format_prompt_for_image_edit_api(
    task_prompt: str,
    system_prompt: str = "",
    negative_prompt: str = "",
) -> dict[str, str]:
    parts = [task_prompt]
    if negative_prompt:
        parts.append(f"Do NOT: {negative_prompt}")
    return {
        "system_prompt": system_prompt,
        "task_prompt": task_prompt,
        "negative_prompt": negative_prompt,
        "api_prompt": "\n\n".join(parts),
    }
