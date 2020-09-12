#!/usr/bin/env python3

# Copyright 2020 The Mumble Developers. All rights reserved.
# Use of this source code is governed by a BSD-style license
# that can be found in the LICENSE file at the root of the
# Mumble source tree or at <https://www.mumble.info/LICENSE>.


import argparse
import re
from datetime import datetime
import os

def comment_remover(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ""
        else:
            return s
    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    return re.sub(pattern, replacer, text)

def fix_lineEnding(text):
    # Convert from Windows to Unix
    text = text.replace("\r\n", "\n")
    # Convert from old Mac to Unix
    text = text.replace("\r", "\n")

    return text

def create_disclaimerComment():
    return "// This file was auto-generated by scripts/generateIceWrapper.py on " + datetime.now().strftime("%Y-%m-%d") + " -- DO NOT EDIT MANUALLY!\n"

def generateFunction(className, functionName, wrapArgs, callArgs):
    function = "void ::Murmur::" + className + "I::" + functionName + "_async(" + (", ".join(wrapArgs)) + ") {\n"
    function += "\t// qWarning() << \"" + functionName + "\" << meta->mp.qsIceSecretRead.isNull() << meta->mp.qsIceSecretRead.isEmpty();\n"
    function += "#ifndef ACCESS_" + className + "_" + functionName + "_ALL\n"
    function += "#\tifdef ACCESS_" + className + "_" + functionName + "_READ\n"
    function += "\tif (!meta->mp.qsIceSecretRead.isNull()) {\n"
    function += "\t\tbool ok = !meta->mp.qsIceSecretRead.isEmpty();\n"
    function += "#\telse\n"
    function += "\tif (!meta->mp.qsIceSecretRead.isNull() || !meta->mp.qsIceSecretWrite.isNull()) {\n"
    function += "\t\tbool ok = !meta->mp.qsIceSecretWrite.isEmpty();\n"
    function += "#\tendif // ACCESS_" + className + "_" + functionName + "_READ\n"
    function += "\t\t::Ice::Context::const_iterator i = current.ctx.find(\"secret\");\n"
    function += "\t\tok = ok && (i != current.ctx.end());\n"
    function += "\t\tif (ok) {\n"
    function += "\t\t\tconst QString &secret = u8((*i).second);\n"
    function += "#\tifdef ACCESS_" + className + "_" + functionName + "_READ\n"
    function += "\t\t\tok = ((secret == meta->mp.qsIceSecretRead) || (secret == meta->mp.qsIceSecretWrite));\n"
    function += "#\telse\n"
    function += "\t\t\tok = (secret == meta->mp.qsIceSecretWrite);\n"
    function += "#\tendif // ACCESS_" + className + "_" + functionName + "_READ\n"
    function += "\t\t}\n"
    function += "\n"
    function += "\t\tif (!ok) {\n"
    function += "\t\t\tcb->ice_exception(InvalidSecretException());\n"
    function += "\t\t\treturn;\n"
    function += "\t\t}\n"
    function += "\t}\n"
    function += "#endif // ACCESS_" + className + "_" + functionName + "_ALL\n"
    function += "\n"
    function += "\tExecEvent *ie = new ExecEvent(boost::bind(&impl_" + className + "_" + functionName + ", " + ", ".join(callArgs) + "));\n"
    function += "\tQCoreApplication::instance()->postEvent(mi, ie);\n"
    function += "}\n"

    return function


def main():
    parser = argparse.ArgumentParser(description="Generates the wrapper files needed for the ICE server-interface")
    parser.add_argument("-i", "--ice-file", help="Path to the ICE specification file (*.ice)", metavar="PATH")
    parser.add_argument("-g", "--generated-ice-header", help="Path to the header file that was generated by ICE", metavar="PATH")
    parser.add_argument("-o", "--out-file", help="Path to the file to write the generated output to. If omitted, the content will be written to std::out", metavar="PATH")
    parser.add_argument("-q", "--quiet", action="store_true", help="Don't display used file paths")

    args = parser.parse_args()

    scriptPath = os.path.realpath(__file__)
    rootDir = os.path.dirname(os.path.dirname(scriptPath))

    if args.ice_file is None:
        # Try to figure out the path to the ice-file (Murmur.ice)
        args.ice_file = os.path.join(rootDir, "src", "murmur", "Murmur.ice")
    if args.generated_ice_header is None:
        # Try to figure out path to the generated header file (in the build dir)
        args.generated_ice_header = os.path.join(rootDir, "build", "src", "murmur", "Murmur.h")

    if not args.quiet:
        print("Using ICE-file at                   \"%s\"" % args.ice_file)
        print("Using ICE-generated header file at  \"%s\"" % args.generated_ice_header)


    iceSpec = fix_lineEnding(open(args.ice_file, "r").read())
    generatedIceHeader = fix_lineEnding(open(args.generated_ice_header, "r").read())

    # remove comments from the iceSpec
    iceSpec = comment_remover(iceSpec)
    # Remove all tabs from iceSpec
    iceSpec = iceSpec.replace("\t", "")
    # Remove empty lines form iceSpec
    iceSpec = iceSpec.replace("\n\n", "\n")

    # Escape all special characters so that iceSpec can be used in a std::string ctor
    iceSpec = iceSpec.replace("\"", "\\\"") # quotes
    iceSpec = iceSpec.replace("\n", "\\n")  # newlines

    wrapperContent = create_disclaimerComment()

    # Include boost-bind as we'll need it later
    wrapperContent += "\n#include <boost/bind/bind.hpp>\n\n"


    className = ""
    responseTypes = {}
    for currentLine in generatedIceHeader.split("\n"):
        currentLine = currentLine.strip()

        if not currentLine:
            # Skip empty lines
            continue

        # find class name
        match = re.match("^class\s+AMD_(.+)\s+:\s+(?:public\svirtual|virtual\s+public)\s+::Ice(?:::AMDCallback|Util::Shared)", currentLine)
        if match:
            className = "AMD_" + match.group(1)

        match = re.match("virtual\s+void\s+ice_response\\((.*)\\)\s+=\s+0;", currentLine)
        if match:
            if not className:
                raise RuntimeError("Expected a className to be found at this time")
        match = re.match("virtual\s+void\s+(.+)_async\(const\s+(.+?)&\s*\w*,(.*)\s+const\s+::Ice::Current&", currentLine)
        if match:
            functionName = match.group(1)
            objectName = match.group(2)
            arguments = match.group(3)

            if functionName == "getSlice":
                # getSlice is handled separately
                continue

            targetClass = "Server" if "AMD_Server" in objectName else "Meta"

            wrapArgs = []
            callArgs = []
            argIndex = 0

            wrapArgs.append("const %s &cb" % objectName)
            callArgs.append("cb")

            if targetClass == "Server":
                callArgs.append("QString::fromStdString(current.id.name).toInt()")
            else:
                callArgs.append("current.adapter")

            for currentArg in arguments.split(","):
                if not currentArg:
                    # skip empty entries
                    continue

                parts = currentArg.split()
                if len(parts) > 1:
                    lastPart = parts[len(parts) - 1]

                    if not ":" in lastPart and not "&" in lastPart:
                        # Omit the last part as it is only a parameter name. We however want the parameters
                        # to be named p1, p2, ... which we'll do below
                        currentArg = " ".join(parts[:len(parts) - 1])

                    if len(currentArg.split()) == 1 and currentArg == "const":
                        # Failsafe in order for us to not only leave const as the type
                        # We have to include lastPart after all
                        currentArg += " " + lastPart

                argIndex += 1
                wrapArgs.append("%s p%d" % (currentArg, argIndex))
                callArgs.append("p%d" % argIndex)

            wrapArgs.append("const ::Ice::Current &current")

            wrapperContent += generateFunction(targetClass, functionName, wrapArgs, callArgs) + "\n"


    wrapperContent += "void ::Murmur::MetaI::getSlice_async(const ::Murmur::AMD_Meta_getSlicePtr &cb, const Ice::Current&) {\n"
    wrapperContent += "\tcb->ice_response(std::string(\"" + iceSpec + "\"));\n"
    wrapperContent += "}\n"


    if args.out_file is None:
        # Write to std::out
        print(wrapperContent)
    else:
        # Write to file
        outFile = open(args.out_file, "w")
        outFile.write(wrapperContent)



main()
