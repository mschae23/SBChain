# region Init
import enum
import hashlib
from io import TextIOWrapper
import time
import os
import json
from flask import Flask, request, jsonify, Response, send_file
from dotenv import load_dotenv
from sys import exit as sys_exit
from typing import Generator, Tuple, Dict, List, Any, TypedDict

app = Flask(__name__)
# Load .env file for the server token
load_dotenv()
SERVER_TOKEN: str | None = os.getenv('SERVER_TOKEN')
# endregion

# region Classes


class TransactionDict(TypedDict):
    sender: str
    receiver: str
    amount: int
    method: str

class BlockDict(TypedDict):
    index: int
    timestamp: float
    data: List[str | Dict[str, TransactionDict]]
    previous_hash: str
    nonce: int
    hash: str

class Block:
    def __init__(self,
                 index: int,
                 data: List[str | Dict[str, TransactionDict]],
                 previous_hash: str,
                 timestamp: float = 0.0,
                 nonce: int = 0,
                 block_hash: str | None = None) -> None:
        self.index: int = index
        self.timestamp: float = timestamp if timestamp else time.time()
        self.data: List[str | Dict[str, TransactionDict]] = data
        self.previous_hash: str = previous_hash
        self.nonce = nonce
        self.hash: str = block_hash if block_hash else self.calculate_hash()

    def calculate_hash(self) -> str:
        block_contents: str = f"{self.index}{self.timestamp}{
            self.data}{self.previous_hash}{self.nonce}"
        hash_string: str = hashlib.sha256(block_contents.encode()).hexdigest()
        # print(f"Hash: {hash_string}")
        return hash_string

    def mine_block(self, difficulty: int) -> None:
        target: str = "0" * difficulty  # Create a string of zeros
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()


class Blockchain:
    # region Chain init
    def __init__(self,
                 blockchain_file_name: str = "data/blockchain.json",
                 transactions_file_name: str = "data/transactions.tsv") -> None:
        self.blockchain_file_name: str = blockchain_file_name
        self.transactions_file_name: str = transactions_file_name
        file_exists: bool = os.path.exists(blockchain_file_name)
        file_empty: bool = file_exists and os.stat(blockchain_file_name).st_size == 0
        if not file_exists or file_empty:
            self.create_genesis_block()

    def create_genesis_block(self) -> None:
        # genesis_block = Block(0, "Genesis Block", "0")
        genesis_block = Block(
            0,
            ["Jiraph complained about not being able to access nn block so I "
            "called Jiraph a scraper"],
            "0"
        )
        self.write_block_to_file(genesis_block)
    # endregion

    # region Block ops
    def write_block_to_file(self, block: Block) -> None:
        # Open the file in append mode
        with open(self.blockchain_file_name, "a") as file:
            # Convert the block object to dictionary, serialize it to JSON, and write it to the file with a newline
            file.write(json.dumps(block.__dict__) + "\n")

    def add_block(
            self,
            data: List[str | Dict[str, TransactionDict]],
            difficulty: int = 0) -> None:
        latest_block: None | Block = self.get_last_block()
        new_block = Block(
            index=(latest_block.index + 1) if latest_block else 0,
            data=data,
            previous_hash=latest_block.hash if latest_block else "0"
        )
        if difficulty > 0:
            new_block.mine_block(difficulty)
        for item in new_block.data:
            if isinstance(item, dict) and "transaction" in item:
                transaction: TransactionDict = item["transaction"]
                # TODO Add hash for each transaction
                self.store_transaction(
                    new_block.timestamp,
                    transaction["sender"],
                    transaction["receiver"],
                    transaction["amount"],
                    transaction["method"]
                )
        self.write_block_to_file(new_block)
    # endregion

    # region Tx ops
    def store_transaction(
            self,
            timestamp: float,
            sender: str,
            receiver: str,
            amount: int,
            method: str) -> None:
        file_existed: bool = os.path.exists(self.transactions_file_name)
        if not file_existed:
            self.create_transactions_file()
            
        with open(self.transactions_file_name, "a") as file:
            file.write(
                f"{timestamp}\t{sender}\t{receiver}\t{amount}\t{method}\n")

    def create_transactions_file(self) -> None:
        with open(self.transactions_file_name, "w") as file:
            file.write("Time\tSender\tReceiver\tAmount\tMethod\n")
    # endregion

    # Block ops 2
    def dict_to_block(self, block_dict: BlockDict) -> Block:
        # Create a new block object from a dictionary
        return Block(
            index=block_dict["index"],
            timestamp=block_dict["timestamp"],
            data=block_dict["data"],
            previous_hash=block_dict["previous_hash"],
            nonce=block_dict["nonce"],
            block_hash=block_dict["hash"]
        )
    
    def load_block(self, json_block: str) -> Block:
        # Deserialize JSON data to a dictionary
        block_dict: BlockDict = json.loads(json_block)
        # Create a new block object from the dictionary
        block: Block = self.dict_to_block(block_dict)
        return block
    # endregion

    # region Tx file valid
    def is_transactions_file_valid(
            self,
            repair: bool = False,
            force: bool = False) -> Tuple[str, bool]:
        """
        Validates the transactions file against the blockchain file.
        By default, the function will only validate the files and print the
        results. No changes will be made.
        # [x] Test (validation passed)
        # [x] Test (validation failed)
        # [x] Test (file not found)

        Returns:
        Bool

        Parameter
        repair
            # [x] Test
            If True, transactions missing from the transactions file will be
            added from the blockchain file.
            # [x] Test
            Unless force is also True, operation will stop if it encounters
            any inconsistencies between the files (beyond missing transactions
            at the end of the transactions file).
            # [x] Test
            If the file does not exist or is empty, a new file will be created.
            Default is False.

        Parameter
        force
            # [x] Test
            If True, the function will create a new transactions file if it does
            not exist or is empty.
            # [x] Test
            If both repair and force are True, any data in the transactions file
            that is inconsistent with the blockchain file will be replaced.
            This may result in the loss of data in the transactions file.

            Default is False.
        """
        
        def line_generator(file: TextIOWrapper) -> Generator[Tuple[int, str], None, None]:
            while True:
                position: int = file.tell()
                line: str = file.readline().strip()  # Read one line at a time
                if not line:  # Break when EOF is reached
                    break
                yield position, line
        
        class Mode(enum.Enum):
            # See if the transactions file matches the blockchain
            VALIDATE = "validate"
            # Copy transactions transactions from the blockchain to the transactions file
            APPEND = "append"

        finished_early_message: str = "Transaction file validation has finished."
        return_message: str = "If you are receiving this message, something went wrong."
        mode: Mode = Mode.VALIDATE
        file_existed: bool = os.path.exists(self.transactions_file_name)
        file_empty: bool = False
        tf_open_text_mode = "r" # Allow reading only
        if file_existed:
            # [x] Test
            print("Transactions file found.")
            file_empty: bool = os.stat(self.transactions_file_name).st_size == 0
            print(f"repair: {repair}")
            print(f"force: {force}")
            if (repair or force):
                tf_open_text_mode = "r+" # Allow reading and writing
            if (file_empty) and (repair or force):
                # [x] Test (force but not repair)
                print("Transactions file is empty. It will be replaced.")
                os.remove(self.transactions_file_name)
                self.create_transactions_file()
                mode = Mode.APPEND
            elif file_empty:
                # [x] Test
                return_message = "Transactions file is empty."
                print(return_message)
                print(finished_early_message)
                return (return_message, False)
        else:
            if force or repair:
                # [x] Test
                print("Transaction file not found. A new file will be created.")
                self.create_transactions_file()
                mode = Mode.APPEND
                tf_open_text_mode = "a+" # Allow appending and reading
            else:
                # [x] Test
                return_message = "Transaction file not found."
                print(return_message)
                print(finished_early_message)
                return (return_message, False)

        with open(self.blockchain_file_name, "r") as bcf, open(self.transactions_file_name, tf_open_text_mode) as tf:
            tf_lines: Generator[Tuple[int, str], None, None] = line_generator(tf)

            # Read the first line (column headers)
            tf_position: int | None = None
            tf_line: str | None = None
            tf_position, tf_line = next(tf_lines, (None, None))
            
            # Read the second line
            tf_position, tf_line = next(tf_lines, (None, None))
            for line in bcf:
                block: Block = self.load_block(line)
                data_list: List[str | Dict[str, TransactionDict]] = block.data
                for item in data_list:
                    if isinstance(item, dict) and "transaction" in item:
                        bcf_transaction: TransactionDict = item["transaction"]
                        # print(f"bcf_transaction: {bcf_transaction}")
                        bcf_timestamp: float = block.timestamp
                        if mode == Mode.VALIDATE:
                            if tf_line is None:
                                print("Expected data in the transactions file was not found.")
                                # print(f"bcf_timestamp: {bcf_timestamp}")
                                # print(f"data: '{bcf_transaction}'")
                                if repair:
                                    # [x] Test (only header columns)
                                    # [x] Test (some data)
                                    print("Data will be appended to the transactions file.")
                                    mode = Mode.APPEND
                                else:
                                    # [x] Test (only header columns)
                                    # [x] Test (some data)
                                    return_message = "The transactions file is missing data."
                                    print(return_message)
                                    print(finished_early_message)
                                    return (return_message, False)
                            else:
                                tf_line_columns_list: List[str] = tf_line.split("\t")
                                # print(f"tf_line_columns_list: [{tf_line_columns_list}]")
                                column_count: int = len(tf_line_columns_list)
                                if column_count != 5:
                                    # [x] Test
                                    return_message = "Invalid transaction format."
                                    print(return_message)
                                    if repair and force:
                                        # [x] Test
                                        print("Contents of the transactions file will be replaced.")
                                        # Clear the file from current point to end
                                        tf.truncate()
                                        mode = Mode.APPEND
                                    else:
                                        # [x] Test
                                        print(finished_early_message)
                                        return (return_message, False)
                                else:
                                    tf_line_transaction_time = float(tf_line_columns_list[0])
                                    # print(f"tf_line_transaction_time: {tf_line_transaction_time}")
                                    # print(f"bcf_timestamp: {bcf_timestamp}")
                                    # print(f"tf_line_transaction_time == bcf_timestamp: {tf_line_transaction_time == bcf_timestamp}")
                                    tf_line_transaction_sender: str = tf_line_columns_list[1]
                                    # print(f"tf_line_transaction_sender: {tf_line_transaction_sender}")
                                    # print("bcf_transaction[\"sender\"]: {}".format(bcf_transaction["sender"]))
                                    # print(f"tf_line_transaction_sender == bcf_transaction[\"sender\"]: {tf_line_transaction_sender == bcf_transaction['sender']}")
                                    tf_line_transaction_receiver: str = tf_line_columns_list[2]
                                    # print(f"tf_line_transaction_receiver: {tf_line_transaction_receiver}")
                                    # print("bcf_transaction[\"receiver\"]: {}".format(bcf_transaction["receiver"]))
                                    # print(f"tf_line_transaction_receiver == bcf_transaction[\"receiver\"]: {tf_line_transaction_receiver == bcf_transaction['receiver']}")
                                    tf_line_transaction_amount: int = int(tf_line_columns_list[3])
                                    # print(f"tf_line_transaction_amount: {tf_line_transaction_amount}")
                                    # print("bcf_transaction[\"amount\"]: {}".format(bcf_transaction["amount"]))
                                    # print(f"tf_line_transaction_amount == bcf_transaction[\"amount\"]: {tf_line_transaction_amount == bcf_transaction['amount']}")
                                    tf_line_transaction_method: str = tf_line_columns_list[4]
                                    # print(f"tf_line_transaction_method: '{tf_line_transaction_method}'")
                                    # print("bcf_transaction[\"method\"]: '{}'".format(bcf_transaction["method"]))
                                    # print(f"tf_line_transaction_method == bcf_transaction[\"method\"]: {tf_line_transaction_method == bcf_transaction['method']}")
                                
                                    # Check if the transaction in the blockchain matches the transaction in the file
                                    if (bcf_timestamp == tf_line_transaction_time and
                                        bcf_transaction["sender"] == tf_line_transaction_sender and
                                        bcf_transaction["receiver"] == tf_line_transaction_receiver and
                                        bcf_transaction["amount"] == tf_line_transaction_amount and
                                        bcf_transaction["method"] == tf_line_transaction_method):
                                        # [x] Test
                                        print("Transaction found.")
                                    else: 
                                        return_message = "Transaction data in the transactions file does not match the blockchain."
                                        print(return_message)
                                        if repair and force:
                                            # [x] Test
                                            print("Contents of the transactions file will be replaced.")
                                            # print(f"position: {tf_position}")
                                            tf.truncate(tf_position)
                                            mode = Mode.APPEND
                                        else:
                                            # [x] Test (default)
                                            # [x] Test (repair)
                                            # [x] Test (force)
                                            print(finished_early_message)
                                            return (return_message, False)
                        if mode == Mode.APPEND:
                            # [x] Test
                            self.store_transaction(
                                block.timestamp,
                                bcf_transaction["sender"],
                                bcf_transaction["receiver"],
                                bcf_transaction["amount"],
                                bcf_transaction["method"]
                            )
                        # Prepare the next line in the transactions file
                        tf_position, tf_line = next(tf_lines, (None, None))
            if (tf_line is not None) and (repair and force):
            # [x] Test
                print("Extra data found in the transactions file. It will be removed.")
                tf.truncate(tf_position)
            elif tf_line is not None:
            # [x] Test
                return_message = "Extra data found in the transactions file."
                print(return_message)
                print(finished_early_message)
                return (return_message, False)
            # [x] Test (validated)
            # [x] Test (appended)
            return_message = "The transactions file is valid."
            print(return_message)
            return (return_message, True)

    # region Chain utils
    def get_chain_length(self) -> int:
        # Open the blockchain file in read binary mode (faster than normal read)
        with open(self.blockchain_file_name, "rb") as file:
            # Count the number of lines and return the count
            return sum(1 for _ in file)

    def get_last_block(self) -> None | Block:
        if not os.path.exists(self.blockchain_file_name):
            return None
        # Get the last line of the file
        with open(self.blockchain_file_name, "rb") as file:
            # Go to the second last byte
            file.seek(-2, os.SEEK_END)
            try:
                # Seek backwards until a newline is found
                # Move one byte at a time
                while file.read(1) != b"\n":
                    # Look two bytes back
                    file.seek(-2, os.SEEK_CUR)
            except OSError:
                # Move to the start of the file if for example no newline is found
                file.seek(0)
            last_line: str = file.readline().decode()

        for block_key in [json.loads(last_line)]:
            return Block(
                index=block_key["index"],
                timestamp=block_key["timestamp"],
                data=block_key["data"],
                previous_hash=block_key["previous_hash"],
                nonce=block_key["nonce"],
                block_hash=block_key["hash"]
            )
    # endregion

    # region Chain valid
    def is_chain_valid(self) -> bool:
        chain_validity = True
        if not os.path.exists(self.blockchain_file_name):
            chain_validity = False
        else:
            current_block: None | Block = None
            previous_block: None | Block = None
            # Open the blockchain file
            with open(self.blockchain_file_name, "r") as file:
                for line in file:
                    if current_block:
                        previous_block = current_block
                    # Load the line as a block
                    current_block = self.load_block(line)
                    # Calculate the hash of the current block
                    calculated_hash: str = current_block.calculate_hash()
                    print(f"\nCurrent block's \"Hash\": {current_block.hash}")
                    print(f"Calculated hash:\t{calculated_hash}")
                    if current_block.hash != calculated_hash:
                        print(f"Block {current_block.index}'s hash does not match the calculated "
                              "hash. This could mean that a block has been tampered with.")
                        chain_validity = False
                        break
                    else:
                        print(f"Block {current_block.index}'s hash matches "
                              "the calculated hash.")
                    if previous_block:
                        print(f"\nPrevious block's hash:\t\t\t{
                              previous_block.hash}")
                        print(f"Current block's \"Previous Hash\":\t{
                            current_block.previous_hash}")
                        if current_block.previous_hash != previous_block.hash:
                            print(f"Block {current_block.index} \"Previous Hash\" value does not "
                                  "match the previous block's hash. This could mean that a block is "
                                  "missing or that one has been incorrectly inserted.")
                            chain_validity = False
                            break
                        else:
                            print(f"Block {current_block.index}  \"Previous Hash\" value matches "
                                  "the previous block's hash.")
        if chain_validity:
            print("The blockchain is valid.")
            return True
        else:
            print("The blockchain is invalid.")
            return False
    # endregion


# region Start chain
blockchain = Blockchain()
# endregion


# region API Routes


@app.route("/add_block", methods=["POST"])
# API Route: Add a new block to the blockchain
def add_block() -> Tuple[Response, int]:
    token: str | None = request.headers.get("token")
    if not token:
        return jsonify({"message": "Token is required."}), 400
    if token != SERVER_TOKEN:
        return jsonify({"message": "Invalid token."}), 400

    data: (
        List[str | Dict[str, TransactionDict]]) = request.get_json().get("data")
    if not data:
        return jsonify({"message": "Data is required."}), 400

    blockchain.add_block(data)
    try:
        last_block: None | Block = blockchain.get_last_block()
        if last_block and last_block.data != data:
            return jsonify({"message": "Block could not be added."}), 500
        else:
            return jsonify({"message": "Block added successfully.",
                            "block": last_block.__dict__}), 200
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"message": "An error occurred."}), 500


@app.route("/get_chain", methods=["GET"])
# API Route: Get the blockchain
def get_chain() -> Tuple[Response, int]:
    print("Retrieving blockchain...")
    with open(blockchain.blockchain_file_name, "r") as file:
        chain_data: list[dict[str, Any]] = [
            json.loads(line) for line in file.readlines()]
        print("Blockchain retrieved.")
        return jsonify({"length": len(chain_data), "chain": chain_data}), 200
    
@app.route("/download_chain", methods=["GET"])
# API Route: Download the blockchain
def download_chain() -> Tuple[Response | Any, int]:
    file_exists: bool = os.path.exists(blockchain.blockchain_file_name)
    if not file_exists:
        return jsonify({"message": "No blockchain found."}), 404
    else:
        return send_file(blockchain.blockchain_file_name, as_attachment=True), 200


@app.route("/get_last_block", methods=["GET"])
# API Route: Get the last block of the blockchain
def get_last_block() -> Tuple[Response, int]:
    last_block: None | Block = blockchain.get_last_block()
    if last_block:
        return jsonify({"block": last_block.__dict__}), 200
    else:
        return jsonify({"message": "No blocks found."}), 404


@app.route("/validate_chain", methods=["GET"])
# API Route: Validate the blockchain
def validate_chain() -> Tuple[Response | Dict[str, str], int]:
    is_valid: bool = blockchain.is_chain_valid()
    return jsonify({"message": "The blockchain is valid." if is_valid else
                    "The blockchain is not valid."}), 200


@app.route("/validate_transactions", methods=["GET"])
# API Route: Validate the blockchain
def validate_transactions() -> Tuple[Response | Dict[str, str], int]:
    token: str | None = request.headers.get("token")
    repair: bool = request.args.get("repair", "false").lower() == "true"
    force: bool = request.args.get("force", "false").lower() == "true"
    message: str
    is_valid: bool
    if token:
        message, is_valid = blockchain.is_transactions_file_valid(repair, force)
    else:
        message, is_valid = blockchain.is_transactions_file_valid(force)
        
    
    return jsonify({"message": message}), 200 if is_valid else 400


@app.route("/shutdown", methods=["POST"])
# API Route: Shutdown the Flask app
def shutdown() -> Tuple[Response, int]:
    try:
        token: str | None = request.headers.get("token")
        if not token:
            return jsonify({"message": "Token is required."}), 400
        if token != SERVER_TOKEN:
            return jsonify({"message": f"Invalid token."}), 400
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"message": "An error occurred."}), 500

    print("The blockchain app will now exit.")
    sys_exit(0)


@app.route("/download_transactions", methods=["GET"])
# API Route: Download the transactions file
def download_transactions() -> Tuple[Response | Any, int]:
    file_exists: bool = os.path.exists(blockchain.transactions_file_name)
    if not file_exists:
        return jsonify({"message": "No transactions found."}), 404
    else:
        return send_file(blockchain.transactions_file_name, as_attachment=True), 200
# endregion


# region Run Flask app
if __name__ == "__main__":
    app.run(port=8080, debug=True)
# endregion
