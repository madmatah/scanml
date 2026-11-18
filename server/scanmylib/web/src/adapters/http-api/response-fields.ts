export class ResponseShapeError extends Error {
  override readonly name = 'ResponseShapeError';

  constructor(field: string) {
    super(`The api's answer holds no valid ${field}`);
  }
}

export interface ResponseFields {
  object(name: string): ResponseFields;
  nullableObject(name: string): ResponseFields | null;
  string(name: string): string;
  nullableString(name: string): string | null;
  number(name: string): number;
  nullableNumber(name: string): number | null;
  boolean(name: string): boolean;
}

function isObject(json: unknown): json is { readonly [name: string]: unknown } {
  return typeof json === 'object' && json !== null && !Array.isArray(json);
}

function readFields(json: unknown, path: string): ResponseFields {
  if (!isObject(json)) throw new ResponseShapeError(path === '' ? 'body' : path);
  const fields = json;
  const pathOf = (name: string) => (path === '' ? name : `${path}.${name}`);

  function read<Field>(name: string, isValid: (field: unknown) => field is Field): Field {
    const field = fields[name];
    if (!isValid(field)) throw new ResponseShapeError(pathOf(name));
    return field;
  }

  const isString = (field: unknown): field is string => typeof field === 'string';
  const isNumber = (field: unknown): field is number => typeof field === 'number' && Number.isFinite(field);

  return {
    object: (name) => readFields(fields[name], pathOf(name)),
    nullableObject: (name) => (fields[name] === null ? null : readFields(fields[name], pathOf(name))),
    string: (name) => read(name, isString),
    nullableString: (name) => read(name, (field): field is string | null => field === null || isString(field)),
    number: (name) => read(name, isNumber),
    nullableNumber: (name) => read(name, (field): field is number | null => field === null || isNumber(field)),
    boolean: (name) => read(name, (field): field is boolean => typeof field === 'boolean'),
  };
}

export function readResponseFields(body: unknown): ResponseFields {
  return readFields(body, '');
}
