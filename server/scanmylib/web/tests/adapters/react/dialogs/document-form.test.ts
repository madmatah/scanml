import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  type DocumentForm,
  newDocumentForm,
  type SubmittedForm,
  submittedForm,
  withKind,
  withUnwarp,
} from '../../../../src/adapters/react/dialogs/document-form.ts';

describe('The document form', () => {
  describe('The newDocumentForm() function', () => {
    let form: DocumentForm;
    beforeEach(() => {
      form = newDocumentForm();
    });

    it('should start as an empty book whose curved pages are flattened', () => {
      assert.deepEqual(form, { title: '', author: '', kind: 'book', unwarp: true, isUnwarpChosen: false });
    });
  });

  describe('The withKind() function', () => {
    describe('When the user has not chosen whether to flatten the pages', () => {
      let form: DocumentForm;
      beforeEach(() => {
        form = withKind(newDocumentForm(), 'document');
      });

      it('should stop flattening them for a document that lies flat', () => {
        assert.equal(form.unwarp, false);
      });
    });

    describe('When the user has chosen to flatten the pages', () => {
      let form: DocumentForm;
      beforeEach(() => {
        form = withKind(withUnwarp(newDocumentForm(), true), 'document');
      });

      it('should keep the choice', () => {
        assert.equal(form.unwarp, true);
      });
    });

    describe('When the user has chosen not to flatten the pages of a book', () => {
      let form: DocumentForm;
      beforeEach(() => {
        form = withKind(withKind(withUnwarp(newDocumentForm(), false), 'document'), 'book');
      });

      it('should keep the choice when the kind comes back to a book', () => {
        assert.equal(form.unwarp, false);
      });
    });
  });

  describe('The submittedForm() function', () => {
    describe('When the title and the author are typed with spaces around them', () => {
      let submitted: SubmittedForm;
      beforeEach(() => {
        submitted = submittedForm({ ...newDocumentForm(), title: '  Example Book ', author: ' Jane Doe  ' });
      });

      it('should send them without the spaces, with the kind and the choice to flatten', () => {
        assert.deepEqual(submitted, {
          fields: { title: 'Example Book', author: 'Jane Doe', kind: 'book', unwarp: true },
        });
      });
    });

    describe('When the title is blank', () => {
      let submitted: SubmittedForm;
      beforeEach(() => {
        submitted = submittedForm({ ...newDocumentForm(), title: '   ', author: 'Jane Doe' });
      });

      it('should refuse it, naming the title as missing', () => {
        assert.deepEqual(submitted, { missing: 'title' });
      });
    });
  });
});
