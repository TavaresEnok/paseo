/**
 * The shared question card sends a multi-select answer as one string: the checked option
 * labels in click order, then any typed answer, joined with ", ". Consume exact option
 * labels from the front, longest first so a label containing ", " wins over its prefix;
 * any remaining text is the typed answer.
 */
export declare function splitMultiSelectAnswer(answer: string, labels: string[]): {
    selected: string[];
    custom: string | null;
};
//# sourceMappingURL=question-card-answer.d.ts.map