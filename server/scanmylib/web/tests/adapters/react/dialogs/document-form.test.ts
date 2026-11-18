import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import {
  type DocumentForm,
  type EditedDocument,
  editedDocumentForm,
  newDocumentForm,
  type SubmittedForm,
  submittedForm,
  withKind,
  withUnwarp,
} from '../../../../src/adapters/react/dialogs/document-form.ts';

describe('The document form', () => {
  describe('The newDocumentForm() function', () => {
    describe('When the form has no field for the notes', () => {
      let form: DocumentForm;
      beforeEach(() => {
        form = newDocumentForm();
      });

      it('should start as an empty book whose curved pages are flattened, without notes', () => {
        assert.deepEqual(form, {
          title: '',
          author: '',
          kind: 'book',
          unwarp: true,
          isUnwarpChosen: false,
          notes: null,
        });
      });
    });

    describe('When the form has a field for the notes', () => {
      let form: DocumentForm;
      beforeEach(() => {
        form = newDocumentForm(true);
      });

      it('should start with empty notes', () => {
        assert.equal(form.notes, '');
      });
    });
  });

  describe('The editedDocumentForm() function', () => {
    const document: EditedDocument = {
      title: 'Example Book',
      author: 'Jane Doe',
      kind: 'document',
      unwarp: true,
      notes: 'Second edition',
    };

    describe('When the document is edited with its notes', () => {
      let form: DocumentForm;
      beforeEach(() => {
        form = editedDocumentForm(document, true);
      });

      it('should start from its current values, its choice to flatten the pages taken as made', () => {
        assert.deepEqual(form, {
          title: 'Example Book',
          author: 'Jane Doe',
          kind: 'document',
          unwarp: true,
          isUnwarpChosen: true,
          notes: 'Second edition',
        });
      });
    });

    describe('When the kind of the edited document changes', () => {
      let form: DocumentForm;
      beforeEach(() => {
        form = withKind(editedDocumentForm({ ...document, kind: 'book', unwarp: true }, true), 'document');
      });

      it('should keep its choice to flatten the pages', () => {
        assert.equal(form.unwarp, true);
      });
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

    describe('When the notes are typed with spaces around them', () => {
      let submitted: SubmittedForm;
      beforeEach(() => {
        submitted = submittedForm({ ...newDocumentForm(true), title: 'Example Book', notes: '\n Second edition \n' });
      });

      it('should send them without the spaces', () => {
        assert.deepEqual(submitted, {
          fields: { title: 'Example Book', author: '', kind: 'book', unwarp: true, notes: 'Second edition' },
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
