import { type FormEvent, type RefObject, useEffect, useRef } from 'react';

import { type PageDetails, readPageNumberEntry, typedNumberOf } from '../../../domain/page-details.ts';

export interface PageNumberFieldOptions {
  readonly isBusy: boolean;
  readonly onSaveNumber: (number: number) => void;
  readonly onInvalidNumber: () => void;
}

export interface PageNumberField {
  readonly input: RefObject<HTMLInputElement | null>;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export const usePageNumberField = (
  page: PageDetails,
  { isBusy, onSaveNumber, onInvalidNumber }: PageNumberFieldOptions,
): PageNumberField => {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const numberInput = input.current;
    if (numberInput === null || document.activeElement === numberInput) return;
    const typedNumber = typedNumberOf(page);
    numberInput.value = typedNumber === null ? '' : String(typedNumber);
  }, [page]);

  const saveNumber = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const numberInput = input.current;
    if (isBusy || numberInput === null) return;
    const entry = readPageNumberEntry(numberInput.value);
    if (entry.isValid) {
      onSaveNumber(entry.number);
    } else {
      onInvalidNumber();
      numberInput.focus();
    }
  };

  return { input, onSubmit: saveNumber };
};
