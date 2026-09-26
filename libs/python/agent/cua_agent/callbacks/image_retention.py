"""
Image retention callback handler that limits the number of recent images in message history.
"""

from typing import Any, Dict, List, Optional

from .base import AsyncCallbackHandler


class ImageRetentionCallback(AsyncCallbackHandler):
    """
    Callback handler that applies image retention policy to limit the number
    of recent images in message history to prevent context window overflow.
    """

    def __init__(self, only_n_most_recent_images: Optional[int] = None):
        """
        Initialize the image retention callback.

        Args:
            only_n_most_recent_images: If set, only keep the N most recent images in message history
        """
        self.only_n_most_recent_images = only_n_most_recent_images

    async def on_llm_start(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply image retention policy to messages before sending to agent loop.

        Args:
            messages: List of message dictionaries

        Returns:
            List of messages with image retention policy applied
        """
        if self.only_n_most_recent_images is None:
            return messages

        return self._apply_image_retention(messages)

    def _apply_image_retention(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply image retention policy to keep only the N most recent images.

        Removes computer_call_output items with image_url and their corresponding computer_call items,
        keeping only the most recent N image pairs based on only_n_most_recent_images setting.

        Args:
            messages: List of message dictionaries

        Returns:
            Filtered list of messages with image retention applied
        """
        if self.only_n_most_recent_images is None:
            return messages

        # Gather indices of all computer_call_output messages that contain an image_url
        output_indices: List[int] = []
        for idx, msg in enumerate(messages):
            if msg.get("type") == "computer_call_output":
                out = msg.get("output")
                if isinstance(out, dict) and ("image_url" in out):
                    output_indices.append(idx)

        # Nothing to trim
        if len(output_indices) <= self.only_n_most_recent_images:
            return messages

        # Determine which outputs to keep (most recent N)
        keep_output_indices = set(output_indices[-self.only_n_most_recent_images :])

        # Build set of indices to remove in one pass
        to_remove: set[int] = set()

        for idx in output_indices:
            if idx in keep_output_indices:
                continue  # keep this screenshot and its context

            to_remove.add(idx)  # remove the computer_call_output itself

            # Find the computer_call with the matching call_id. It is not
            # guaranteed to sit immediately before its output (batched turns
            # emit [call A, call B, output A, output B]; resumed histories can
            # interleave arbitrarily), so scan backward instead of assuming
            # idx - 1. Leaving the call behind would send an unpaired
            # computer_call that the Responses API rejects on the next step.
            call_id = messages[idx].get("call_id")
            call_idx: Optional[int] = None
            for j in range(idx - 1, -1, -1):
                m = messages[j]
                if (
                    isinstance(m, dict)
                    and m.get("type") == "computer_call"
                    and m.get("call_id") == call_id
                ):
                    call_idx = j
                    break
            if call_idx is not None:
                to_remove.add(call_idx)
                # Check a single reasoning immediately before that computer_call
                r_idx = call_idx - 1
                if (
                    r_idx >= 0
                    and isinstance(messages[r_idx], dict)
                    and messages[r_idx].get("type") == "reasoning"
                ):
                    to_remove.add(r_idx)

        # Construct filtered list
        filtered = [m for i, m in enumerate(messages) if i not in to_remove]
        return filtered
