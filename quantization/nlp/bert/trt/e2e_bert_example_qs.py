import os
import onnx
import onnxruntime
import numpy as np
import json
import collections
import data_processing as dp
import tokenization
from pathlib import Path
import subprocess
from onnxruntime.quantization import CalibrationDataReader, create_calibrator, CalibrationMethod, write_calibration_table, QuantType, QuantizationMode, QDQQuantizer, quantize_static, QuantFormat
import argparse
from pathlib import Path
import sys
import logging



class BertDataReader(CalibrationDataReader):
    def __init__(self,
                 model_path,
                 squad_json,
                 vocab_file,
                 batch_size,
                 max_seq_length,
                 doc_stride,
                 start_index=0,
                 end_index=0):
        self.model_path = model_path
        self.data = dp.read_squad_json(squad_json)
        self.max_seq_length = max_seq_length
        self.batch_size = batch_size
        self.example_stride = batch_size # number of examples as one example stride. (set to equal to batch size) 
        self.start_index = start_index # squad example index to start with
        self.end_index = len(self.data) if end_index == 0 else end_index 
        self.current_example_index = start_index
        self.current_feature_index = 0 # global feature index (one example can have more than one feature) 
        self.tokenizer = tokenization.BertTokenizer(vocab_file=vocab_file, do_lower_case=True)
        self.doc_stride = doc_stride 
        self.max_query_length = 64
        self.enum_data_dicts = iter([])
        self.features_list = []
        self.token_list = []
        self.example_id_list = []
        self.start_of_new_stride = False # flag to inform that it's a start of new example stride

    def get_next(self):
        iter_data = next(self.enum_data_dicts, None)
        if iter_data:
            self.start_of_new_stride= False
            return iter_data

        self.enum_data_dicts = None
        if self.current_example_index >= self.end_index:
            print("Reading dataset is done. Total examples is {:}".format(self.end_index-self.start_index))
            return None
        elif self.current_example_index + self.example_stride > self.end_index:
            self.example_stride = self.end_index - self.current_example_index

        if self.current_example_index % 10 == 0:
            current_batch = int(self.current_feature_index / self.batch_size) 
            print("Reading example index {:}, batch {:}, containing {:} sentences".format(self.current_example_index, current_batch, self.batch_size))

        # example could have more than one feature
        # we collect all the features of examples and process them in one example stride
        features_in_current_stride = []
        for i in range(self.example_stride):
            example = self.data[self.current_example_index+ i]
            features = dp.convert_example_to_features(example.doc_tokens, example.question_text, self.tokenizer, self.max_seq_length, self.doc_stride, self.max_query_length)
            self.example_id_list.append(example.id)
            self.features_list.append(features)
            self.token_list.append(example.doc_tokens)
            features_in_current_stride += features
        self.current_example_index += self.example_stride
        self.current_feature_index+= len(features_in_current_stride)


        # following layout shows three examples as example stride with batch size 2:
        # 
        # start of new example stride 
        # |
        # |
        # v
        # <--------------------- batch size 2 ---------------------->
        # |...example n, feature 1....||...example n, feature 2.....| 
        # |...example n, feature 3....||...example n+1, feature 1...| 
        # |...example n+1, feature 2..||...example n+1, feature 3...|
        # |...example n+1, feature 4..||...example n+2, feature 1...|

        data = []
        for feature_idx in range(0, len(features_in_current_stride), self.batch_size):
            input_ids = []
            input_mask = []
            segment_ids = []

            for i in range(self.batch_size):
                if feature_idx + i >= len(features_in_current_stride):
                    break
                feature = features_in_current_stride[feature_idx + i]
                if len(input_ids) and len(segment_ids) and len(input_mask):
                    input_ids = np.vstack([input_ids, feature.input_ids])
                    input_mask = np.vstack([input_mask, feature.input_mask])
                    segment_ids = np.vstack([segment_ids, feature.segment_ids])
                else:
                    input_ids = np.expand_dims(feature.input_ids, axis=0)
                    input_mask = np.expand_dims(feature.input_mask, axis=0)
                    segment_ids = np.expand_dims(feature.segment_ids, axis=0)

            data.append({"input_ids": input_ids, "attention_mask": input_mask})# "token_type_ids":segment_ids})
            # data.append({"input_ids": input_ids, "input_mask": input_mask, "segment_ids":segment_ids})

        self.enum_data_dicts = iter(data)
        self.start_of_new_stride = True
        return next(self.enum_data_dicts, None)

def get_predictions(example_id_in_current_stride,
                    features_in_current_stride,
                    token_list_in_current_stride,
                    batch_size,
                    outputs,
                    _NetworkOutput,
                    all_predictions):
                    
    if example_id_in_current_stride == []:
        return 

    base_feature_idx = 0
    for idx, id in enumerate(example_id_in_current_stride):
        features = features_in_current_stride[idx]
        doc_tokens = token_list_in_current_stride[idx]
        networkOutputs = []
        for i in range(len(features)):
            x = (base_feature_idx + i) // batch_size
            y = (base_feature_idx + i) % batch_size

            output = outputs[x]
            start_logits = output[0][y]
            end_logits = output[1][y]

            networkOutputs.append(_NetworkOutput(
                start_logits = start_logits,
                end_logits = end_logits,
                feature_index = i 
                ))

        base_feature_idx += len(features) 

        # Total number of n-best predictions to generate in the nbest_predictions.json output file
        n_best_size = 20

        # The maximum length of an answer that can be generated. This is needed
        # because the start and end predictions are not conditioned on one another
        max_answer_length = 30

        prediction, nbest_json, scores_diff_json = dp.get_predictions(doc_tokens, features,
                networkOutputs, n_best_size, max_answer_length)

        all_predictions[id] = prediction

# def inference(data_reader, ort_session):

#     _NetworkOutput = collections.namedtuple(  # pylint: disable=invalid-name
#             "NetworkOutput",
#             ["start_logits", "end_logits", "feature_index"])
#     all_predictions = collections.OrderedDict()
    
#     example_id_in_current_stride = [] 
#     features_in_current_stride = []  
#     token_list_in_current_stride = []
#     outputs = []
#     while True:
#         inputs = data_reader.get_next()
#         if not inputs:
#             break

#         if data_reader.start_of_new_stride:
#             get_predictions(example_id_in_current_stride, features_in_current_stride, token_list_in_current_stride, data_reader.batch_size, outputs, _NetworkOutput, all_predictions)

#             # reset current example stride
#             example_id_in_current_stride = data_reader.example_id_list[-data_reader.example_stride:]
#             features_in_current_stride = data_reader.features_list[-data_reader.example_stride:] 
#             token_list_in_current_stride = data_reader.token_list[-data_reader.example_stride:]
#             outputs = []

#         output = ort_session.run(["output_start_logits","output_end_logits"], inputs)
#         outputs.append(output)


#     # handle the last example stride
#     get_predictions(example_id_in_current_stride, features_in_current_stride, token_list_in_current_stride, data_reader.batch_size, outputs, _NetworkOutput, all_predictions)

#     return all_predictions

def get_op_nodes_not_followed_by_specific_op(model, op1, op2):
    op1_nodes = []
    op2_nodes = []
    selected_op1_nodes = []
    not_selected_op1_nodes = []

    for node in model.graph.node:
        if node.op_type == op1:
            op1_nodes.append(node)
        if node.op_type == op2:
            op2_nodes.append(node)

    for op1_node in op1_nodes:
        for op2_node in op2_nodes:
            if op1_node.output == op2_node.input:
                selected_op1_nodes.append(op1_node.name)
        if op1_node.name not in selected_op1_nodes:
            not_selected_op1_nodes.append(op1_node.name)

    return not_selected_op1_nodes

from onnxruntime.quantization import CalibrationDataReader
class OnnxQuantizerDataReader(CalibrationDataReader):
    def __init__(self, enum_data_dicts):
        # the 'enum_data_dicts' should be a list of dict
        self.enum_data_dicts = iter(enum_data_dicts)

    def get_next(self):
        return next(self.enum_data_dicts, None)
    

if __name__ == '__main__':
    '''
    BERT QDQ Quantization for TensorRT.

    There are two steps for the quantization,
    first, calibration is done based on SQuAD dataset to get dynamic range of floating point tensors in the model
    second, Q/DQ nodes with dynamic range (scale and zero-point) are inserted to the model

    The onnx model used in the script is converted from Hugging Face BERT model,
    https://huggingface.co/transformers/serialization.html#converting-an-onnx-model-using-the-transformers-onnx-package

    Some utility functions for dataset processing, data reader and evaluation are from Nvidia TensorRT demo BERT repo,
    https://github.com/NVIDIA/TensorRT/tree/master/demo/BERT
    '''
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--target",  type=str, default="cpu", choices=["cpu", "ipu"], help="which target to run the models")
    args = parser.parse_args().__dict__
    target: str = args.pop("target")

    logger = logging.getLogger("Relay_Build")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(sys.stdout))


    # Model, dataset and quantization settings
    input_model_path = "./distilbert_base_uncased_squad_onnx/model.onnx"
    squad_json = "./squad/dev-v1.1.json" #calibrate dataset
    # squad_json = "./squad/dev-v2.0.json" # uncomment it if you want to use squad v2.0 as dataset
    vocab_file = "./squad/vocab.txt"
    augmented_model_path = "./augmented_model.onnx"
    qdq_model_path = "./qdq_model.onnx"
    sequence_lengths = [384, 128] # if use sequence length 384 then choose doc stride 128. if use sequence length 128 then choose doc stride 32.   
    doc_stride = [128, 32]
    calib_num = 20
    op_types_to_quantize = ['Sub', 'Mul', 'Unsqueeze', 'Conv', 'Relu', 'Transpose', 'Reshape', 'MatMul', 'Add', 'ReduceMean', 'Pow', 'Sqrt', 'Div', 'Gather', 'Split', 'Concat', 'Slice', 'ReduceMin', 'Softmax', 'Tanh', 'Squeeze', 'Gemm']#['MatMul', 'Add']
    batch_size = 1

    # Generate INT8 calibration cache
    print("Calibration starts ...")
    calibrator = create_calibrator(input_model_path, op_types_to_quantize, augmented_model_path=augmented_model_path, calibrate_method=CalibrationMethod.Percentile)
    calibrator.set_execution_providers(["CPUExecutionProvider"]) 

    '''
    We can use one data reader to do data pre-processing, however,
    some machines don't have sufficient memory to hold all dataset and all intermediate output,
    especially using 'Entropy' or 'Percentile' calibrator which collects histogram for tensors.
    So let multiple data readers to handle different stride of dataset to avoid OOM.
    '''
    stride = 10
    for i in range(0, calib_num, stride):
        data_reader = BertDataReader(input_model_path, squad_json, vocab_file, batch_size, sequence_lengths[-1], doc_stride[-1], start_index=i, end_index=(i+stride))
        calibrator.collect_data(data_reader)

    compute_range = calibrator.compute_range()
    #write_calibration_table(json.loads(compute_range))
    print("Calibration is done. Calibration cache is saved to calibration.json")

    # Generate QDQ model
    mode = QuantizationMode.QLinearOps

    model = onnx.load_model(Path(input_model_path), 'protobuf')

    # In TRT, it recommended to add QDQ pair to inputs of Add node followed by ReduceMean node.
    nodes_to_exclude = [] 
    
    quantize_static(augmented_model_path,
                    qdq_model_path,
                    OnnxQuantizerDataReader(compute_range),
                    quant_format=QuantFormat.QDQ,
                    per_channel=False, # Read from Json file
                    nodes_to_exclude = nodes_to_exclude,
                    weight_type=QuantType.QInt8, # Read from Json file
                    activation_type=QuantType.QInt8, # Read from Json file
                    extra_options={"DedicatedQDQPair": True, "ForceQuantizeNoInputCheck": True, "MatMulConstBOnly": False ,"WeightSymmetric": False}, # Read from Json file and append more extra_options
                    calibrate_method=CalibrationMethod.Percentile,
                    op_types_to_quantize=op_types_to_quantize)
    print("QDQ model is saved to ", qdq_model_path)

    # QDQ model inference and get SQUAD prediction 
    batch_size = 1 
    data_reader = BertDataReader(qdq_model_path, squad_json, vocab_file, batch_size, sequence_lengths[-1], doc_stride[-1])
    sess_options = onnxruntime.SessionOptions()

    if target == "cpu":
        provider = "CPUExecutionProvider"
        provider_options = {}
    else:
        provider = "VitisAIExecutionProvider"
        cache_dir = Path(__file__).parent.resolve()
        provider_options = {
            'config_file': '.\\other_libs_qdq\\vaip_config_gemm_asr_decoder.json',
            'cacheDir': str(cache_dir),
            'cacheKey': 'modelcachekey'
        }
        sess_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
        #sess_options.add_session_config_entry("session.disable_quant_qdq", "1")

    sess = onnxruntime.InferenceSession(qdq_model_path, providers=[provider,],sess_options=sess_options,provider_options=[provider_options],)
    print(sess)
    # all_predictions = inference(data_reader, session) 

