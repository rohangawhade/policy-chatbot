import { useState } from "react";

import { submitFeedback, type FeedbackRating } from "../../api/chat";

interface FeedbackButtonsProps {
  messageId: string;
}

export function FeedbackButtons({ messageId }: FeedbackButtonsProps) {
  const [submitted, setSubmitted] = useState<FeedbackRating | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleClick(rating: FeedbackRating) {
    if (submitted || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await submitFeedback(messageId, rating);
      setSubmitted(rating);
    } catch {
      // Feedback is a nice-to-have signal, not a blocking action -- a
      // failed submit just leaves the buttons clickable again rather
      // than surfacing an error to the user.
    } finally {
      setIsSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <p className="text-xs text-gray-500">
        {submitted === "thumbs_up" ? "Thanks for the feedback!" : "Thanks, we'll look into it."}
      </p>
    );
  }

  return (
    <div className="flex gap-2">
      <button
        type="button"
        aria-label="Thumbs up"
        disabled={isSubmitting}
        onClick={() => void handleClick("thumbs_up")}
        className="rounded px-1.5 py-0.5 text-gray-500 hover:bg-gray-200 disabled:opacity-50"
      >
        👍
      </button>
      <button
        type="button"
        aria-label="Thumbs down"
        disabled={isSubmitting}
        onClick={() => void handleClick("thumbs_down")}
        className="rounded px-1.5 py-0.5 text-gray-500 hover:bg-gray-200 disabled:opacity-50"
      >
        👎
      </button>
    </div>
  );
}
