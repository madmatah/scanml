export class ResponseShapeError extends Error {
  override readonly name = 'ResponseShapeError';

  constructor(field: string) {
    super(`The api's answer holds no valid ${field}`);
  }
}

// An address of the api reaches an <img> or a link as it is: it may only name one of the api's own files.
const API_PATH_PREFIX = '/api/';

export interface ResponseFields {
  object(name: string): ResponseFields;
  nullableObject(name: string): ResponseFields | null;
  string(name: string): string;
  nullableString(name: string): string | null;
  number(name: string): number;
  nullableNumber(name: string): number | null;
  boolean(name: string): boolean;
  apiPath(name: string): string;
  nullableApiPath(name: string): string | null;
  objectList(name: string): ResponseFields[];
  numberPairs(name: string): (readonly [number, number])[];
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
  const isApiPath = (field: unknown): field is string => isString(field) && field.startsWith(API_PATH_PREFIX);
  const isNumber = (field: unknown): field is number => typeof field === 'number' && Number.isFinite(field);

  function readList(name: string): readonly unknown[] {
    const field = fields[name];
    if (!Array.isArray(field)) throw new ResponseShapeError(pathOf(name));
    return field;
  }

  function readNumberPair(pair: unknown, path: string): readonly [number, number] {
    if (!Array.isArray(pair) || pair.length !== 2) throw new ResponseShapeError(path);
    const [first, second]: readonly unknown[] = pair;
    if (!isNumber(first) || !isNumber(second)) throw new ResponseShapeError(path);
    return [first, second];
  }

  return {
    object: (name) => readFields(fields[name], pathOf(name)),
    nullableObject: (name) => (fields[name] === null ? null : readFields(fields[name], pathOf(name))),
    string: (name) => read(name, isString),
    nullableString: (name) => read(name, (field): field is string | null => field === null || isString(field)),
    number: (name) => read(name, isNumber),
    nullableNumber: (name) => read(name, (field): field is number | null => field === null || isNumber(field)),
    boolean: (name) => read(name, (field): field is boolean => typeof field === 'boolean'),
    apiPath: (name) => read(name, isApiPath),
    nullableApiPath: (name) => read(name, (field): field is string | null => field === null || isApiPath(field)),
    objectList: (name) => readList(name).map((entry, index) => readFields(entry, `${pathOf(name)}[${index}]`)),
    numberPairs: (name) => readList(name).map((pair, index) => readNumberPair(pair, `${pathOf(name)}[${index}]`)),
  };
}

export function readResponseFields(body: unknown): ResponseFields {
  return readFields(body, '');
}
