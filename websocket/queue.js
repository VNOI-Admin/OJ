// Source: https://github.com/skeggse/qu/blob/master/lib/qu.js (this code was not licensed at the time of writing).
// @ts-check
/**
 * @template T
 */
class Item {
  /**
   * @param {T} data
   * @param {Item<T> | null} next
   */
  constructor(data, next) {
    /**
     * The item's data.
     * @type {T}
     * @public
     */
    this.data = data;
    /**
     * The item's next adjacent item.
     * @type {Item<T> | null}
     * @public
     */
    this.next = next;
  }
}

/**
 * @template T
 */
export class Queue {
  /**
   * The queue's head.
   * @type {Item<T> | null}
   */
  #head;
  /**
   * The queue's tail.
   * @type {Item<T> | null}
   */
  #tail;
  /**
   * The queue's length.
   * @type {number}
   */
  #length;
  constructor() {
    this.#head = null;
    this.#tail = null;
    this.#length = 0;
  }
  /**
   * @template T
   * @param {T[]} array
   * @returns {Queue<T>}
   */
  static fromArray(array) {
    const queue = new Queue();
    for (let i = 0; i < array.length; i++) {
      queue.push(array[i]);
    }
    return queue;
  }
  toArray() {
    const array = new Array(this.length);
    for (let item = this.#head, i = 0; item; item = item.next) {
      array[i++] = item.data;
    }
    return array;
  }
  /**
   * Adds an item to the queue.
   * @param {T} data
   * @returns
   */
  push(data) {
    const prev = this.#tail;
    this.#tail = new Item(data, null);
    if (prev) {
      prev.next = this.#tail;
    } else {
      this.#head = this.#tail;
    }
    this.#length++;
    return this;
  }
  /**
   * Removes an item from the queue and returns it.
   */
  pop() {
    const data = this.#head?.data;
    this.#head = this.#head?.next || null;
    if (!this.#head) {
      this.#tail = null;
    }
    this.#length--;
    return data;
  }
  /**
   * Adds an item to the queue.
   * @param {T} data
   * @returns
   */
  unshift(data) {
    this.#head = new Item(data, this.#head);
    if (!this.#tail) {
      this.#tail = this.#head;
    }
    this.#length++;
    return this;
  }
  /**
   * Loops through the queue.
   * @param {((data: T, index: number) => void)} fn
   */
  forEach(fn) {
    for (let item = this.#head, i = 0; item; item = item.next) {
      fn(item.data, i++);
    }
  }
  get length() {
    return this.#length;
  }
  get head() {
    return this.#head?.data;
  }
  get tail() {
    return this.#tail?.data;
  }
}

export default Queue;
