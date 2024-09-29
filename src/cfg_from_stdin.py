from antlr4 import CommonTokenStream, StdinStream, FileStream
from antlr.gen.JavaLexer import JavaLexer
from antlr.gen.JavaParser import JavaParser
from src.cfg_extractor.cfg_extractor_visitor import CFGExtractorVisitor
from src.graph.visual import draw_CFG
import os
from networkx import to_dict_of_dicts
from pathlib import Path

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def find_java_files(directory):
    """
    Recursively finds Java files in the given directory and yields project number and Java file number.

    :param directory: Root directory to start searching from.
    :yield: Tuples containing the project number and the Java file number within each project.
    """
    return [str(filename) for filename in Path(directory).rglob('*.java')]


def prompt():
    project_name = input("Enter your Project Name[1_tulibee]: ")
    is_verbose = input("Verbose graph draw (y/n)? ").startswith(("y", "Y"))
    test_source_directory = ROOT_DIR + "/test_source/sf-poject/SF110-20130704-src/"
    file_path = "1_tullibee"
    test_source_directory = test_source_directory + project_name + "/src/main/" if project_name else test_source_directory + file_path + "/src/main/"

    return is_verbose, test_source_directory, project_name if project_name else file_path


def extract(stream):
    lexer = JavaLexer(stream)
    token_stream = CommonTokenStream(lexer)
    parser = JavaParser(token_stream)
    parse_tree = parser.compilationUnit()
    cfg_extractor = CFGExtractorVisitor()
    cfg_extractor.visit(parse_tree)
    funcs = cfg_extractor.functions
    LastNodes = cfg_extractor.functionLastNode
    return funcs, token_stream, LastNodes


def makedir(directory):
    try:
        os.makedirs(directory)

    except OSError as error:
        print(error)


def main():
    is_verbose, project_path, project_name = prompt()
    files = find_java_files(project_path)
    makedir(f"test_output/{project_name}")
    for file in files:
        makedir(f"test_output/{project_name}/{Path(file).stem}")
        stream = FileStream(file, encoding="utf8")
        funcs, token_stream, end_nodes = extract(stream)
        for g in funcs.items():
            makedir(f"test_output/{project_name}/{Path(file).stem}/{g[0]}")
            draw_CFG(g[1], end_nodes[g[0]], f"test_output/{project_name}/{Path(file).stem}/{g[0]}/{g[0]}", token_stream,
                     verbose=is_verbose)

# def main():
#     stream = FileStream('/Users/a.kazor/PycharmProjects/java-visitor/test_source/sf-poject/SF110-20130704-src/1_tullibee/src/main/java/com/ib/client/EReader.java', encoding="utf8")
#     funcs, token_stream, end_nodes = extract(stream)
#     for g in funcs.items():
#         draw_CFG(g[1], end_nodes, f"test_output/0", token_stream,
#                  verbose=True)


if __name__ == '__main__':
    main()
